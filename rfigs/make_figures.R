# Render the four main figures from the canonical result CSVs -- R/ggplot2
# Data sources and design tokens are identical to tools/make_figures.py.
# Output: figures_r/  (preview; --install copies into the submission chain)
#
# Run: Rscript rfigs/make_figures.R [--install]

suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(readr); library(scales)
  library(patchwork); library(grid); library(tools)
})

args   <- commandArgs(TRUE)
root   <- normalizePath(getwd())
source(file.path(root, "rfigs", "figstyle.R"))

OUT      <- file.path(root, "figures_r")
do_install <- "--install" %in% args

# ------------------------------------------------------------------ Fig 1 ---
fig1_forest <- function() {
  d <- read_csv(file.path(root, "results_full", "table3_focus_signals.csv"),
                show_col_types = FALSE)
  d <- d %>%
    filter(is.finite(ROR), ROR > 0, is.finite(ROR025), is.finite(ROR975)) %>%
    arrange(ROR) %>% tail(25) %>%
    mutate(label = toTitleCase(tolower(PT)),
           row   = dplyr::row_number() - 1,
           lab   = ifelse(is_robust_signal, "Robust signal (4/4 algorithms)",
                          "Signal not robust"))

  XMAX <- 150
  off  <- d$ROR975 > XMAX
  d$plot_r <- pmin(d$ROR, XMAX * 0.93)
  d$lo <- pmin(pmax(d$ROR025, 0.3), XMAX)
  d$hi <- pmin(d$ROR975, XMAX)

  n <- nrow(d)
  ylim <- c(-0.8, n + 0.8)

  pal <- c("Robust signal (4/4 algorithms)" = SIGNAL,
           "Signal not robust"              = NEUTRAL,
           "ROR = 1 (null)"                 = MUTED,
           "95% CI (truncated at axis edge)" = CICOL)

  p1 <- ggplot(d) +
    # CI whiskers (legend key)
    geom_segment(aes(x = lo, xend = hi, y = row, yend = row,
                     colour = "95% CI (truncated at axis edge)"),
                 linewidth = 0.28, show.legend = TRUE) +
    # truncation arrows where the CI runs off the axis (no legend key)
    geom_segment(data = d[off, ],
                 aes(x = XMAX * 0.93, xend = XMAX * 0.99, y = row, yend = row),
                 colour = CICOL, linewidth = 0.28, show.legend = FALSE,
                 arrow = arrow(length = unit(4, "pt"), type = "closed")) +
    geom_point(aes(x = plot_r, y = row, colour = lab), size = 1.25, stroke = 0) +
    # null line (legend key)
    geom_vline(aes(xintercept = 1, colour = "ROR = 1 (null)"),
               linewidth = 0.25, linetype = "33") +
    scale_colour_manual(values = pal, name = NULL, drop = FALSE) +
    scale_x_log10(limits = c(0.3, XMAX * 1.02), labels = comma) +
    scale_y_continuous(limits = ylim, breaks = 0:(n - 1), labels = d$label,
                       expand = c(0, 0)) +
    labs(x = "Reporting odds ratio (log scale; whiskers, 95% CI)", y = NULL) +
    theme_pub() +
    theme(panel.grid.major.y = element_blank(),
          axis.text.y  = element_text(size = 6.5),
          axis.ticks.y = element_blank(),
          axis.line.y  = element_blank(),
          legend.position = c(0.98, 0.02), legend.justification = c(1, 0),
          legend.text.align = 0,
          legend.key.height = unit(7, "pt"), legend.key.width = unit(16, "pt"),
          legend.margin = margin(0, 0, 0, 0))

  # right-hand count columns, synced through patchwork
  counts <- data.frame(row = d$row, cases = comma(d$a), rest = comma(d$c))
  hdr_y  <- n + 0.35
  txt_panel <- function(x, col, hlabel, centered) {
    ggplot(counts, aes(y = row)) +
      annotate("text", x = x, y = hdr_y, label = hlabel, size = 6.5 / .pt,
               fontface = "bold", colour = INK,
               hjust = if (centered) 0.5 else 0) +
      geom_text(aes_string(x = x, label = col), size = 6.5 / .pt,
                colour = MUTED, hjust = if (centered) 0.5 else 0) +
      scale_x_continuous(limits = c(0, 1)) +
      scale_y_continuous(limits = ylim, expand = c(0, 0)) +
      theme_void() + theme(plot.margin = margin(0, 0, 0, 0))
  }

  fig <- p1 +
    txt_panel(0.5, "cases", "Cases", TRUE) +
    txt_panel(0.08, "rest",  "Rest of database", FALSE) +
    plot_layout(widths = c(5.8, 1.1, 2.0)) +
    plot_annotation(caption = paste("Points: ROR. Bars: 95% CI (arrowheads mark CIs truncated at",
                                    "the axis limit). Red: positive signal under all four algorithms;",
                                    "blue: not robust.")) &
    theme(plot.caption = element_text(size = 6.5, colour = MUTED,
                                      hjust = 0, margin = margin(t = 5)))
  save_fig(fig, file.path(OUT, "Figure_1.png"), W_DOUBLE, 0.235 * n + 1.25)
}

# ------------------------------------------------------------------ Fig 2 ---
wilson_pct <- function(k, n, z = 1.959963985) {
  p <- k / n
  d <- 1 + z * z / n
  ctr <- (p + z * z / (2 * n)) / d
  hw  <- z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
  c(pmax(0, (ctr - hw) * 100), pmin(100, (ctr + hw) * 100))
}

fig2_trend <- function() {
  ts <- read_csv(file.path(root, "results_label_change", "ts_quarterly_family.csv"),
                 show_col_types = FALSE)
  quarters <- ts$quarter
  fams <- names(FAMILY_FULL)
  nq <- length(quarters)
  x  <- seq_len(nq) - 1
  i_cut <- match("2025Q3", quarters)   # 1-based; x axis is 0-based

  long <- do.call(rbind, lapply(fams, function(f)
    data.frame(quarter = quarters, x = x, fam = f,
               y = ts[[paste0(f, "_pct")]],
               lo = mapply(function(k, n) wilson_pct(k, n)[1], ts[[f]], ts$n),
               hi = mapply(function(k, n) wilson_pct(k, n)[2], ts[[f]], ts$n))))
  long$fam <- factor(long$fam, levels = fams)   # keep the manuscript's family order

  p_small <- ggplot(long) +
    annotate("rect", xmin = i_cut - 1.5, xmax = nq - 0.5,
             ymin = -Inf, ymax = Inf, fill = BAND) +
    geom_ribbon(aes(x, ymin = lo, ymax = hi, fill = fam), alpha = 0.15,
                colour = NA) +
    geom_line(aes(x, y, colour = fam), linewidth = 0.32) +
    geom_point(aes(x, y, fill = fam), shape = 21, size = 0.8,
               colour = "white", stroke = 0.3) +
    geom_vline(xintercept = i_cut - 1.5, colour = MUTED,
               linewidth = 0.22, linetype = "33") +
    scale_colour_manual(values = FAMILY_COLORS, guide = "none") +
    scale_fill_manual(values = FAMILY_COLORS, guide = "none") +
    facet_wrap(~fam, ncol = 2, scales = "fixed",
               labeller = labeller(fam = function(f)
                 paste0("<span style='color:", FAMILY_COLORS[f], ";'>",
                        FAMILY_FULL[f], "</span>"))) +
    coord_cartesian(ylim = c(0, 40), clip = "off") +
    scale_y_continuous(breaks = c(0, 10, 20, 30, 40)) +
    scale_x_continuous(breaks = x, labels = quarters) +
    labs(x = NULL, y = "Proportion of reports (%)") +
    theme_pub() +
    theme(panel.grid.major.x = element_blank(),
          strip.background = element_blank(),
          strip.placement = "outside",
          strip.text = ggtext::element_markdown(size = 8.5, face = "bold",
                                                hjust = 0),
          axis.text.x = element_text(angle = 60, hjust = 1))

  # denominators: a proportion is unreadable without its base
  den <- data.frame(x = x, n = ts$n, quarter = quarters)
  p_denom <- ggplot(den) +
    annotate("rect", xmin = i_cut - 1.5, xmax = nq - 0.5,
             ymin = -Inf, ymax = Inf, fill = BAND) +
    geom_col(aes(x, n), width = 0.62, fill = "#B7C6D4") +
    geom_text(aes(x, n + max(ts$n) * 0.02, label = comma(n)), size = 5.2 / .pt,
              colour = MUTED, vjust = 0) +
    geom_vline(xintercept = i_cut - 1.5, colour = MUTED,
               linewidth = 0.22, linetype = "33") +
    annotate("text", x = i_cut - 1.05, y = max(ts$n) * 1.13,
             label = "Post-label revision", hjust = 0, colour = MUTED,
             size = 6.5 / .pt, fontface = "italic") +
    scale_y_continuous(breaks = c(0, 500, 1000, 1500, 2000),
                       limits = c(0, max(ts$n) * 1.26)) +
    scale_x_continuous(breaks = x, labels = quarters) +
    labs(x = NULL, y = "Reports (n)", title = "Quarterly denominators") +
    theme_pub() +
    theme(panel.grid.major.x = element_blank(),
          axis.text.x = element_text(angle = 60, hjust = 1),
          plot.title = element_text(size = 8.5, face = "bold",
                                    colour = INK, hjust = 0))

  fig <- p_small + p_denom +
    plot_layout(ncol = 1, heights = c(3, 1.05)) +
    plot_annotation(caption = paste("Panels share a 0-40% scale. Ribbons: 95% Wilson",
                                    "interval. Shaded area: post-label-revision period",
                                    "(2025Q3 onward).")) &
    theme(plot.caption = element_text(size = 6.5, colour = MUTED,
                                      hjust = 0, margin = margin(t = 5)))
  save_fig(fig, file.path(OUT, "Figure_2.png"), W_DOUBLE, 7.3)
}

# ------------------------------------------------------------------ Fig 3 ---
# Merged two-panel version (author pick A1): left = global importance bars,
# right = SHAP beeswarm, both restricted to the top 15 features sharing one
# y order (ascending mean |SHAP|). Replaces the former Table (SHAP importance).
fig3_shap <- function() {
  sv <- read_csv(file.path(root, "results_ml_real", "ml_shap_values.csv"),
                 show_col_types = FALSE)
  ft <- read_csv(file.path(root, "results_ml_real", "ml_feature_table.csv"),
                 show_col_types = FALSE)
  feats <- setdiff(names(sv), SHAP_DROP)
  sv <- sv[, feats]
  imp <- data.frame(feature = names(sv), mean_abs = colMeans(abs(sv))) %>%
    arrange(desc(mean_abs))
  order <- names(sort(colMeans(abs(sv))))   # ascending -> y from bottom up
  n_top <- 15

  NBINS <- 60; LEVELS <- 13; STEP <- 0.055
  pts <- do.call(rbind, lapply(seq_along(order), function(i) {
    f  <- order[i]
    x  <- as.numeric(sv[[f]])
    v  <- as.numeric(ft[[f]])
    uniq <- unique(v[!is.na(v)])
    is_binary <- length(uniq) <= 2
    vmax <- suppressWarnings(max(v[is.finite(v)], na.rm = TRUE))
    vv <- if (is.finite(vmax) && vmax > 0) v / vmax else rep(0, length(v))
    vv[is.na(vv)] <- 0.5     # NaN -> pale centre (mirrors the Python fix)
    if (is_binary) x <- x + (vv - 0.5) * 0.03
    df <- data.frame(x = x)
    if (is_binary) {
      # two clusters only: quantile bins collapse -> just cycle slots
      df$offs <- ((seq_along(x) - 1) %% LEVELS - (LEVELS - 1) / 2) * STEP
    } else {
      bins <- unique(quantile(x, seq(0, 1, length.out = NBINS + 1)))
      if (length(bins) < 2) {
        df$offs <- ((seq_along(x) - 1) %% LEVELS - (LEVELS - 1) / 2) * STEP
      } else {
        idx <- as.integer(cut(x, bins, include.lowest = TRUE, labels = FALSE))
        idx[is.na(idx)] <- 0
        df$bin <- idx
        df$within <- ave(seq_along(x), df$bin, FUN = function(w) seq_along(w) - 1)
        df$offs <- (df$within %% LEVELS - (LEVELS - 1) / 2) * STEP
      }
    }
    data.frame(x = df$x, y = (i - 1) + df$offs, v = vv, f = f)
  }))

  # importance bar panel: same y order as the beeswarm (ascending)
  imp_asc <- imp[order(imp$mean_abs), ] %>% slice_tail(n = n_top) %>%
    mutate(label = {m <- unname(FEATURE_LABELS[feature]); ifelse(is.na(m), feature, m)},
           ypos  = match(feature, tail(order, n_top)) - 1)
  p_bar <- ggplot(imp_asc, aes(mean_abs, ypos)) +
    geom_col(fill = ACCENT, width = 0.62, orientation = "y") +
    scale_y_continuous(breaks = imp_asc$ypos, labels = imp_asc$label,
                       expand = c(0, 0)) +
    scale_x_continuous(expand = expansion(mult = c(0, 0.08))) +
    labs(x = "Mean |SHAP|", y = NULL,
         title = "Feature importance\n(top 15 of 21)") +
    theme_pub() +
    theme(axis.text.y = element_text(size = 6.5),
          axis.ticks.y = element_blank(), axis.line.y = element_blank(),
          panel.grid.major.y = element_blank())

  # beeswarm restricted to the same 15 features
  pts15 <- pts[pts$f %in% tail(order, n_top), ]
  pts15$y <- pts15$y - min(pts15$y)          # re-index to 0..14
  p_swarm <- ggplot(pts15, aes(x, y, colour = v)) +
    geom_vline(xintercept = 0, colour = MUTED, linewidth = 0.25) +
    geom_point(size = 0.4, stroke = 0, alpha = 0.40) +
    scale_colour_gradientn(colours = SHAP_COLS, limits = c(0, 1),
                           breaks = c(0, 1), labels = c("Low", "High"),
                           name = "Feature value",
                           guide = guide_colourbar(barwidth = 1.1,
                                                   barheight = 2.4,
                                                   ticks.linewidth = 0.2)) +
    scale_y_continuous(breaks = 0:(n_top - 1), labels = NULL,
                       expand = c(0, 0)) +
    scale_x_continuous(expand = expansion(mult = c(0.02, 0.02))) +
    labs(x = "SHAP value (impact on model output)", y = NULL,
         title = "SHAP distribution\n(each point: one report)") +
    coord_cartesian(ylim = c(-0.9, n_top - 0.1)) +
    theme_pub() +
    theme(panel.grid = element_blank(),
          plot.margin = margin(2, 8, 10, 2, unit = "pt"))

  fig <- (p_bar | p_swarm) + plot_layout(widths = c(1.0, 1.7)) +
    plot_annotation(caption = paste("Left: mean absolute SHAP value per feature (top 15 of 21). Right: SHAP",
                                    "contributions of individual reports; x: SHAP value in log-odds of\n",
                                    "the composite endpoint; colour: feature value (red high, blue low, grey missing).\n",
                                    "Positivity in the top vs bottom quartile of the female-sex SHAP contribution:",
                                    "12.9% vs 6.2%.\n",
                                    "No feature carries a large effect (highest mean |SHAP| 0.031).")) &
    theme(plot.caption = element_text(size = 6.5, colour = MUTED, hjust = 0,
                                      lineheight = 1.5, margin = margin(t = 5)))
  save_fig(fig, file.path(OUT, "Figure_3.png"), W_DOUBLE, 0.26 * n_top + 1.9)
}

# ------------------------------------------------------------------ Fig 4 ---
fig4_network <- function() {
  ntd <- file.path(root, "results", "network_tox")
  tgt  <- read_csv(file.path(ntd, "predicted_targets.csv"), show_col_types = FALSE) %>% head(3)
  hubs <- read_csv(file.path(ntd, "ppi_hubs.csv"), show_col_types = FALSE) %>% head(12)
  go   <- read_csv(file.path(ntd, "enrichment_go_bp.csv"), show_col_types = FALSE) %>%
    head(10) %>%
    mutate(term = gsub("\\s*\\(GO:\\d+\\)", "", term),
           term_wrap = vapply(term, function(t)
             paste(strwrap(t, 24), collapse = "\n"), character(1)),
           nlp = -log10(pmax(adj_p_value, 1e-300)))

  tgt$hi <- tgt$gene == tgt$gene[which.max(tgt$score)]

  p1 <- ggplot(tgt, aes(score, reorder(gene, score))) +
    geom_col(aes(fill = hi), width = 0.55) +
    scale_fill_manual(values = c(`FALSE` = ACCENT, `TRUE` = SIGNAL), guide = "none") +
    scale_x_continuous(expand = expansion(mult = c(0, 0.05))) +
    labs(x = "Similarity score", y = NULL,
         title = "Predicted targets\n(ChEMBL similarity)") +
    theme_pub() +
    theme(axis.text.y = element_text(size = 7), axis.ticks.y = element_blank(),
          axis.line.y = element_blank(), panel.grid.major.y = element_blank())

  p2 <- ggplot(hubs, aes(degree, reorder(gene, degree))) +
    geom_col(fill = ACCENT, width = 0.6) +
    scale_x_continuous(expand = expansion(mult = c(0, 0.05))) +
    labs(x = "STRING degree", y = NULL, title = "PPI hub genes") +
    theme_pub() +
    theme(axis.text.y = element_text(size = 7), axis.ticks.y = element_blank(),
          axis.line.y = element_blank(), panel.grid.major.y = element_blank())

  p3 <- ggplot(go, aes(nlp, reorder(term_wrap, nlp))) +
    geom_col(fill = ACCENT, width = 0.6) +
    scale_x_continuous(expand = expansion(mult = c(0, 0.05))) +
    labs(x = expression(-log[10]*P[adj]), y = NULL, title = "GO-BP enrichment") +
    theme_pub() +
    theme(axis.text.y = element_text(size = 6.5), axis.ticks.y = element_blank(),
          axis.line.y = element_blank(), panel.grid.major.y = element_blank())

  # KEGG dot-plot panel (author pick B1): merged below the triptych, replacing
  # the former KEGG enrichment table in the main text
  kegg <- read_csv(file.path(ntd, "enrichment_kegg.csv"), show_col_types = FALSE) %>%
    mutate(nlp = -log10(pmax(adj_p_value, 1e-300)),
           term_wrap = vapply(term, function(t)
             paste(strwrap(t, 32), collapse = "\n"), character(1)))
  kegg_n <- 12
  kd <- kegg %>% slice_head(n = kegg_n)
  p_kegg <- ggplot(kd, aes(nlp, reorder(term_wrap, nlp))) +
    geom_point(aes(size = n_overlap, colour = nlp), alpha = 0.85) +
    scale_colour_gradient(low = ACCENT, high = SIGNAL,
                          name = expression(-log[10]*P[adj]),
                          guide = guide_colourbar(barwidth = 1.1,
                                                  barheight = 2.2)) +
    scale_size_continuous(name = "Bridged genes\nin pathway",
                          range = c(1.2, 4.2), breaks = c(20, 40, 60, 80)) +
    scale_x_continuous(expand = expansion(mult = c(0.05, 0.10))) +
    labs(x = expression(-log[10]*P[adj]), y = NULL,
         title = paste0("KEGG pathway enrichment (top ", kegg_n,
                        ", Enrichr BH-corrected)")) +
    theme_pub() +
    theme(axis.text.y = element_text(size = 6.5),
          axis.ticks.y = element_blank(), axis.line.y = element_blank(),
          panel.grid.major.y = element_blank())

  top <- (p1 | p2 | p3) + plot_layout(widths = c(1.0, 1.1, 1.3))
  fig <- top / p_kegg +
    plot_layout(heights = c(1.0, 1.45)) +
    plot_annotation(caption = paste("Top left: max Tanimoto similarity of predicted off-targets to the drug's ChEMBL anchors.",
                                    "Top centre: top hub genes\n",
                                    "by degree in the bridged PPI network. Top right: GO-BP enrichment of bridged genes.",
                                    "Bottom: KEGG pathways of bridged\n",
                                    "genes (Enrichr, BH-corrected); bubble size = bridged genes in pathway,",
                                    "colour = adjusted p.")) &
    theme(plot.caption = element_text(size = 6.5, colour = MUTED,
                                      hjust = 0, lineheight = 1.5,
                                      margin = margin(t = 5)))
  save_fig(fig, file.path(OUT, "Figure_4.png"), W_DOUBLE, 3.35 + 3.3)
}

# ------------------------------------------------------------------ Fig S1 --
figS1_rocpr <- function() {
  cv   <- read_csv(file.path(root, "results_ml_real", "ml_roc_pr_curves.csv"),
                   show_col_types = FALSE)
  comp <- read_csv(file.path(root, "results_ml_real", "ml_model_comparison.csv"),
                   show_col_types = FALSE)
  prev <- comp$prevalence_mean[1]          # out-of-fold positive rate (~10.4%)
  auc  <- setNames(round(comp$auc_mean, 3), comp$model)

  morder <- c("RandomForest", "LogisticRegression", "XGBoost", "LightGBM")
  pal <- c("RandomForest" = SIGNAL, "LogisticRegression" = ACCENT,
           "XGBoost" = "#3D8B6E", "LightGBM" = "#D19A2F")
  cv$model <- factor(cv$model, levels = morder)
  lab <- paste0(morder, " (AUC ", sprintf("%.3f", auc[morder]), ")")
  names(lab) <- morder

  p_roc <- ggplot(cv[cv$curve == "roc", ], aes(x, y, colour = model)) +
    geom_abline(slope = 1, intercept = 0, colour = MUTED,
                linewidth = 0.25, linetype = "22") +
    geom_line(linewidth = 0.32) +
    scale_colour_manual(values = pal, labels = lab, name = NULL, drop = FALSE) +
    scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25)) +
    scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25)) +
    labs(x = "False positive rate", y = "True positive rate",
         title = "ROC (out-of-fold)") +
    theme_pub() +
    theme(legend.position = c(0.98, 0.02), legend.justification = c(1, 0),
          legend.text.align = 0, legend.key.height = unit(7, "pt"))

  p_pr <- ggplot(cv[cv$curve == "pr", ], aes(x, y, colour = model)) +
    geom_hline(yintercept = prev, colour = MUTED, linewidth = 0.25,
               linetype = "22") +
    geom_line(linewidth = 0.32) +
    annotate("text", x = 0.60, y = prev + 0.04,
             label = sprintf("chance (%.1f%%)", 100 * prev),
             size = 6.5 / .pt, colour = MUTED, hjust = 0) +
    scale_colour_manual(values = pal, guide = "none") +
    scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25)) +
    scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25)) +
    labs(x = "Recall", y = "Precision",
         title = "Precision-Recall (out-of-fold)") +
    theme_pub()

  fig <- (p_roc | p_pr) +
    plot_layout(widths = c(1, 1)) +
    plot_annotation(caption = paste("Out-of-fold predictions (5x3 repeated stratified CV).",
                                    "Dashed diagonal: chance (ROC); dashed horizontal: prevalence",
                                    "(precision-recall). AUC values: mean across folds.")) &
    theme(plot.caption = element_text(size = 6.5, colour = MUTED,
                                      hjust = 0, margin = margin(t = 5)))
  save_fig(fig, file.path(OUT, "Supplementary_Figure_S1.png"), W_DOUBLE, 3.5)
}

# ------------------------------------------------------------------ main ----
cat("Rendering to", OUT, "\n")
fig1_forest()
fig2_trend()
fig3_shap()
fig4_network()
figS1_rocpr()

if (do_install) {
  canon <- c("Figure_1.png" = file.path(root, "results_full", "forest_focus.png"),
             "Figure_2.png" = file.path(root, "results_label_change", "label_change_trend.png"),
             "Figure_3.png" = file.path(root, "figures", "shap_summary.png"),
             "Figure_4.png" = file.path(root, "results", "network_tox", "figures", "network_tox_summary.png"),
             "Supplementary_Figure_S1.png" = file.path(root, "figures", "roc_pr_curves.png"))
  for (nm in names(canon)) {
    file.copy(file.path(OUT, nm), canon[[nm]], overwrite = TRUE)
    cat("  [install]", canon[[nm]], "<-", nm, "\n")
  }
}
