# House figure style for the rimegepant manuscript -- R/ggplot2 twin of src/figstyle.py
# Same palette, same type scale, same export rules: the four figures must look
# like one paper whether they come from Python or R.

INK     <- "#1F1F1F"   # text, spines
MUTED   <- "#767676"   # secondary text
GRID    <- "#E8E8E8"   # gridlines
BAND    <- "#F2F2F2"   # shaded period band
CICOL   <- "#B9BEC4"   # confidence-interval whiskers

SIGNAL  <- "#A63446"   # robust signal (crimson, muted)
NEUTRAL <- "#4E6E8E"   # non-signal data ink (slate blue)
ACCENT  <- "#3E6C9E"   # single-hue bars, lines

FAMILY_COLORS <- c(
  "Anaphylactoid"           = "#B94A2C",
  "Systemic hypersensitivity" = "#3E6C9E",
  "Oral mucosal"            = "#3D8B6E",
  "Oral sensory"            = "#D19A2F",
  "Pharyngeal/airway"       = "#8F6793",
  "Excipient reaction"      = "#8C8C8C"
)

FAMILY_FULL <- c(
  "Anaphylactoid"             = "Anaphylactoid reactions",
  "Systemic hypersensitivity" = "Systemic hypersensitivity",
  "Oral mucosal"              = "Oral mucosal",
  "Oral sensory"              = "Oral sensory",
  "Pharyngeal/airway"         = "Pharyngeal/airway",
  "Excipient reaction"        = "Excipient reaction"
)

# SHAP diverging: low feature value (slate) -> mid (pale grey) -> high (crimson)
SHAP_COLS <- c("#3E6C9E", "#D9DDE2", "#A63446")

W_DOUBLE <- 7.2   # journal double column, inches
W_15     <- 5.5   # 1.5 column
W_SINGLE <- 3.5   # single column
DPI      <- 450

FEATURE_LABELS <- c(
  "sex_female" = "Female sex", "sex_missing" = "Sex missing",
  "age" = "Age", "age_missing" = "Age missing", "age_lt18" = "Age < 18",
  "age_ge65" = "Age \u2265 65", "weight" = "Weight", "report_year" = "Report year",
  "country_us" = "Country: United States", "n_drugs" = "Number of drugs",
  "n_aes" = "Number of AEs", "tto_days" = "Time to onset (days)",
  "tto_missing" = "Time to onset missing",
  "combo_antihistamine" = "Concomitant antihistamine",
  "combo_corticosteroid" = "Concomitant corticosteroid",
  "combo_nsaid" = "Concomitant NSAID", "combo_triptan" = "Concomitant triptan",
  "combo_ppi" = "Concomitant PPI", "combo_ssri_snri" = "Concomitant SSRI/SNRI",
  "combo_betablocker" = "Concomitant \u03b2-blocker",
  "combo_anticonvulsant" = "Concomitant antiepileptic",
  "combo_cgrp_mab" = "Concomitant CGRP mAb"
)

SHAP_DROP <- c("sex_male", "report_year_centered")   # mirror / redundant features

#' Journal theme: Arial, 7 pt base, clean spines, light grid, no frame
theme_pub <- function(base_size = 7) {
  theme_bw(base_size = base_size, base_family = "Arial") %+replace%
    theme(
      panel.border   = element_blank(),
      panel.background = element_blank(),
      axis.line      = element_line(colour = INK, linewidth = 0.25),
      axis.ticks     = element_line(colour = INK, linewidth = 0.25),
      axis.ticks.length = unit(2.5, "pt"),
      axis.title     = element_text(colour = INK, size = 8, margin = margin(t = 2, r = 0, b = 0, l = 0)),
      axis.text      = element_text(colour = INK, size = 7),
      panel.grid.minor = element_blank(),
      panel.grid.major = element_line(colour = GRID, linewidth = 0.22),
      legend.frame   = element_blank(),
      legend.text    = element_text(colour = INK, size = 6.5),
      legend.title   = element_text(colour = INK, size = 6.5),
      plot.title     = element_text(colour = INK, size = 8.5, face = "bold", hjust = 0),
      plot.caption   = element_text(colour = MUTED, size = 6.5, hjust = 0)
    )
}

save_fig <- function(p, path, width, height) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  ggsave(path, p, width = width, height = height, dpi = DPI, bg = "white",
         device = ragg::agg_png)
  cat(sprintf("  [fig] %s  (%.0f kB)\n", basename(path),
              file.info(path)$size / 1024))
  invisible(path)
}
