# Risk Space MCP — R analysis example
#
# Demonstrates loading and analysing the published Risk Space MCP data
# using a standard tidyverse + sf workflow.
#
# Tested with: R 4.3+, jsonlite 1.8+, dplyr 1.1+, ggplot2 3.4+, sf 1.0+.

library(jsonlite)
library(dplyr)
library(ggplot2)

base_url <- "https://agentic-governance.github.io/risk-space-dashboard/data"

# ---------------------------------------------------------------------------
# 1. Load grid data
# ---------------------------------------------------------------------------
grid <- fromJSON(paste0(base_url, "/grid_risk.json"))
cat("Loaded", nrow(grid), "grid cells\n")
str(grid)

# ---------------------------------------------------------------------------
# 2. Basic statistics
# ---------------------------------------------------------------------------
summary(grid$expected_harm)

# ---------------------------------------------------------------------------
# 3. Plot distribution
# ---------------------------------------------------------------------------
p <- ggplot(grid, aes(x = expected_harm)) +
  geom_histogram(bins = 50, fill = "steelblue", colour = "white") +
  labs(
    title = "Risk distribution across published cells",
    x = "Expected Harm",
    y = "Count"
  ) +
  theme_minimal()

ggsave("risk_distribution_R.png", p, width = 8, height = 5, dpi = 150)
cat("Saved: risk_distribution_R.png\n")

# ---------------------------------------------------------------------------
# 4. Top-20 cells in Tokyo 23-ku bounding box
# ---------------------------------------------------------------------------
tokyo_top <- grid %>%
  filter(lat >= 35.5, lat <= 35.85,
         lon >= 139.5, lon <= 139.9) %>%
  arrange(desc(expected_harm)) %>%
  head(20)

print(tokyo_top)

# ---------------------------------------------------------------------------
# 5. Spatial join with sf (optional)
# ---------------------------------------------------------------------------
# install.packages("sf") if not installed
library(sf)
grid_sf <- st_as_sf(grid, coords = c("lon", "lat"), crs = 4326)
cat("Created sf object with", nrow(grid_sf), "features\n")

# Spatial correlation: Moran's I (requires spdep)
# library(spdep)
# nb <- dnearneigh(st_coordinates(grid_sf), d1 = 0, d2 = 0.01)
# lw <- nb2listw(nb, style = "W", zero.policy = TRUE)
# moran.test(grid_sf$expected_harm, lw, zero.policy = TRUE)

# ---------------------------------------------------------------------------
# 6. Load haven tile index
# ---------------------------------------------------------------------------
haven_idx <- fromJSON(paste0(base_url, "/haven_tiles/index.json"))
cat("Total haven tiles:", length(haven_idx), "\n")
