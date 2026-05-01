#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request

INPUT_PATH = Path('data/analysis/school_risk_v2/school_profiles_v2.json')
OUTPUT_PATH = Path('data/llm_explanations/school_explanations_today.json')

FORBIDDEN_WORDS = ['予測', '確率', '危険です', '危険な', '安全です', '安全な']
MAX_CHARS = 200
LIFT_VALUE = 27.073

SYSTEM_PROMPT = (
    'あなたは学校安全情報の文章生成アシスタントです。以下ルールを厳守してください。\n'
    '- 「予測」「確率」「危険です」「安全です」「安全な」は絶対に使わない\n'
    '- 「傾向があります」「記録されています」「参考情報」「多い傾向」を使う\n'
    '- 保護者が読んで過度に不安にならない冷静な表現\n'
    '- 具体的な行動提案を1つだけ含める\n'
    '- 200文字以内\n'
    '- 引用や脚注 [1] [2] は不要、本文のみ返す'
)


def load_school_profiles(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('schools', 'data', 'items'):
            value = data.get(key)
            if isinstance(value, list):
                return value
    raise ValueError(f'Unsupported school profile format: {path}')


def extract_high_risk_schools(schools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in schools:
        if bool(s.get('high_risk')) and bool(s.get('in_coverage')):
            out.append(s)
    return out


def build_school_prompt(school: Dict[str, Any], weather: str = 'cloudy', road: str = 'wet') -> str:
    name = school.get('name') or school.get('school_name') or '不明な学校'
    pref = school.get('prefecture') or '不明'
    haven_count = int(school.get('haven_count_500m') or 0)
    risk_level = school.get('risk_level') or 'unknown'
    _base_risk = float(school.get('base_risk') or 0)
    _ = (weather, road, _base_risk)

    return (
        f'以下のデータをもとに、{name}({pref})の本日の下校時間帯に関する参考情報を200文字以内で生成してください。\n\n'
        'データ:\n'
        '- 天候条件: 曇り(路面湿潤の可能性)\n'
        f'- 500m以内の立ち寄り施設数: {haven_count}施設\n'
        f'- 過去データに基づく注意喚起レベル: {risk_level}\n'
        f'- 参考指標: このような天候条件の下校時間帯には過去の記録で歩行中の事故が増える傾向がある(lift={LIFT_VALUE:.1f}倍)\n\n'
        '参考情報本文のみ返してください。引用・脚注は不要です。'
    )


def call_perplexity_chat(api_key: str, user_prompt: str) -> str:
    payload = {
        'model': 'sonar',
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': 300,
        'temperature': 0.3,
    }
    body = json.dumps(payload).encode('utf-8')
    req = request.Request(
        'https://api.perplexity.ai/chat/completions',
        data=body,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='ignore')
        raise RuntimeError(f'HTTP {e.code}: {detail}') from e
    except Exception as e:
        raise RuntimeError(f'Perplexity request failed: {e}') from e

    choices = result.get('choices') or []
    if not choices:
        raise RuntimeError(f'No choices in response: {result}')
    message = (choices[0] or {}).get('message') or {}
    content = str(message.get('content') or '').strip()
    if not content:
        raise RuntimeError('Empty content in response')
    return sanitize_explanation(content)


def sanitize_explanation(text: str) -> str:
    text = text.replace('\n', ' ').strip()
    while '  ' in text:
        text = text.replace('  ', ' ')
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
    return text


def generate_template_explanation(school: Dict[str, Any], weather: str = 'cloudy', road: str = 'wet') -> str:
    haven_count = int(school.get('haven_count_500m') or 0)
    _ = (weather, road)

    weather_note = '今日は曇りで路面が湿っている可能性があります。'
    if haven_count >= 3:
        haven_note = '周辺に立ち寄れる施設が複数あります。'
    elif haven_count >= 1:
        haven_note = '周辺の立ち寄り施設は限られています。'
    else:
        haven_note = '周辺の立ち寄り施設が少ない地区です。'

    fixed = 'このような日の下校時間帯は、過去の記録で事故が増える傾向があります。'
    action = '複数人での帰宅や、人通りの多い道を選ぶことを参考にしてください。'
    footer = '(これは過去の記録に基づく参考情報です)'

    text = f'{weather_note}{haven_note}{fixed}{action}{footer}'
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
    return text


def find_forbidden_words(text: str) -> List[str]:
    return [w for w in FORBIDDEN_WORDS if w in text]


def main() -> None:
    schools = load_school_profiles(INPUT_PATH)
    high_risk_schools = extract_high_risk_schools(schools)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get('PERPLEXITY_API_KEY')
    explanations: Dict[str, Dict[str, Any]] = {}
    forbidden_violations: List[Dict[str, Any]] = []
    char_violations: List[Dict[str, Any]] = []
    char_lengths: List[int] = []

    perplexity_count = 0
    template_count = 0
    sample_perplexity: Optional[str] = None
    sample_template: Optional[str] = None

    for school in high_risk_schools:
        school_id = str(school.get('id') or school.get('school_id') or school.get('name') or f'unknown_{len(explanations)}')
        school_name = school.get('name') or school.get('school_name') or school_id

        source = 'template'
        explanation = ''

        if api_key:
            try:
                user_prompt = build_school_prompt(school)
                explanation = call_perplexity_chat(api_key, user_prompt)
                source = 'perplexity'
                perplexity_count += 1
                if sample_perplexity is None:
                    sample_perplexity = explanation
            except Exception as e:
                explanation = generate_template_explanation(school)
                template_count += 1
                if sample_template is None:
                    sample_template = explanation
                print(f'fallback for {school_name}: {e}')
        else:
            explanation = generate_template_explanation(school)
            template_count += 1
            if sample_template is None:
                sample_template = explanation

        explanation = sanitize_explanation(explanation)
        char_lengths.append(len(explanation))

        bad_words = find_forbidden_words(explanation)
        if bad_words:
            forbidden_violations.append({
                'school_id': school_id,
                'school_name': school_name,
                'words': bad_words,
                'text': explanation,
            })

        if len(explanation) > MAX_CHARS:
            char_violations.append({
                'school_id': school_id,
                'school_name': school_name,
                'char_len': len(explanation),
            })

        explanations[school_id] = {
            'school_name': school_name,
            'prefecture': school.get('prefecture'),
            'lat': school.get('lat'),
            'lon': school.get('lon'),
            'risk_level': school.get('risk_level'),
            'weather': 'cloudy',
            'road_surface': 'wet',
            'explanation': explanation,
            'source': source,
            'generated_at': datetime.now().isoformat(),
        }

        time.sleep(0.3)

    payload = {
        'generated_at': datetime.now().isoformat(),
        'total_target': len(high_risk_schools),
        'generated_count': len(explanations),
        'perplexity_count': perplexity_count,
        'template_count': template_count,
        'forbidden_violations_count': len(forbidden_violations),
        'forbidden_violations': forbidden_violations,
        'char_violations_count': len(char_violations),
        'char_violations': char_violations,
        'explanations': explanations,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    if char_lengths:
        char_min = min(char_lengths)
        char_avg = sum(char_lengths) / len(char_lengths)
        char_max = max(char_lengths)
    else:
        char_min = char_avg = char_max = 0

    print(f'total_target: {len(high_risk_schools)}')
    print(f'generated_count: {len(explanations)}')
    print(f'perplexity_count: {perplexity_count} / template_count: {template_count}')
    print(f'forbidden_violations_count: {len(forbidden_violations)}')
    print(f'char_min / char_avg / char_max: {char_min} / {char_avg:.2f} / {char_max}')
    print(f'sample_perplexity: "{sample_perplexity or ""}"')
    print(f'sample_template: "{sample_template or ""}"')


if __name__ == '__main__':
    main()
