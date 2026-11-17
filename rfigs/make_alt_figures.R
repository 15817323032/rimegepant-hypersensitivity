# Alternative table->figure conversions for review (NOT installed into the
# submission chain). Generates four variants into figures_alt/ so the author
# can pick:
#   A1  Figure 3 merged with a SHAP-importance bar panel   (replaces old Table 8)
#   A2  standalone SHAP-importance bar figure              (replaces old Table 8)
#   B1  Figure 4 extended with a KEGG dot-plot panel       (replaces old Table 10)
#   B2  standalone KEGG dot-plot figure                    (replaces old Table 10)
#
# Run: Rscript rfigs/make_alt_figures.R

suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(readr); library(patchwork)
})

root <- normalizePath(getwd())
source(file.path(root, "rfigs", "figstyle.R"))
ALT <- file.path(root, "figures_alt")
dir.create(ALT, showWarnings = FALSE)
cat("Rendering alternatives to", ALT, "\n")

# ------------------------------------------------------------- SHAP pieces ----
sv <- read_csv(file.path(root, "results_ml_real", "ml_shap_values.csv"),
               show_col_types = FALSE)
ft <- read_csv(file.path(root, "results_ml_real", "ml_feature_table.csv"),
               show_col_types = FALSE)
feats <- setdiff(names(sv), SHAP_DROP)
sv <- sv[, feats]
imp <- data.frame(feature = names(sv),
                  mean_abs = colMeans(abs(sv))) %>%
  arrange(desc(mean_abs))
order <- names(sort(colMeans(abs(sv))))    # ascending -> y from bottom up
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
  vv[is.na(vv)] <- 0.5
  if (is_binary) x <- x + (vv - 0.5) * 0.03
  df <- data.frame(x = x)
  if (is_binary) {
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

# A2: standalone importance bar (top 15, descending from top)
imp_top <- imp %>% slice_head(n = n_top) %>%
  mutate(label = {m <- unname(FEATURE_LABELS[feature]); ifelse(is.na(m), feature, m)})
p_bar_standalone <- ggplot(imp_top, aes(mean_abs, reorder(label, mean_abs))) +
  geom_col(fill = ACCENT, width = 0.62) +
  scale_x_continuous(expand = expansion(mult = c(0, 0.08))) +
  labs(x = "Mean |SHAP| (log-odds)", y = NULL,
       title = "SHAP global feature importance (top 15)") +
  theme_pub() +
  theme(axis.text.y = element_text(size = 7),
        axis.ticks.y = element_blank(), axis.line.y = element_blank(),
        panel.grid.major.y = element_blank())
save_fig(p_bar_standalone, file.path(ALT, "A2_shap_importance_standalone.png"),
         W_15, 0.17 * n_top + 1.0)

# bar panel for the merged variant: same y order as the beeswarm (ascending)
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
n_f15 <- n_top
p_swarm <- ggplot(pts15, aes(x, y, colour = v)) +
  geom_vline(xintercept = 0, colour = MUTED, linewidth = 0.25) +
  geom_point(size = 0.4, stroke = 0, alpha = 0.40) +
  scale_colour_gradientn(colours = SHAP_COLS, limits = c(0, 1),
                         breaks = c(0, 1), labels = c("Low", "High"),
                         name = "Feature value",
                         guide = guide_colourbar(barwidth = 1.1,
                                                 barheight = 2.4,
                                                 ticks.linewidth = 0.2)) +
  scale_y_continuous(breaks = 0:(n_f15 - 1), labels = NULL,
                     expand = c(0, 0)) +
  scale_x_continuous(expand = expansion(mult = c(0.02, 0.02))) +
  labs(x = "SHAP value (impact on model output)", y = NULL,
       title = "SHAP distribution\n(each point: one report)") +
  coord_cartesian(ylim = c(-0.9, n_f15 - 0.1)) +
  theme_pub() +
  theme(panel.grid = element_blank(),
        plot.margin = margin(2, 8, 10, 2, unit = "pt"))

# A1: merged two-panel figure
fig_a1 <- (p_bar | p_swarm) + plot_layout(widths = c(1.0, 1.7)) +
  plot_annotation(caption = paste("Left: mean absolute SHAP value per feature",
                                  "(top 15). Right: SHAP contributions of individual",
                                  "reports; colour: feature value (red high, blue low,",
                                  "grey missing).")) &
  theme(plot.caption = element_text(size = 6.5, colour = MUTED, hjust = 0,
                                    margin = margin(t = 5)))
save_fig(fig_a1, file.path(ALT, "A1_fig3_with_importance.png"),
         W_DOUBLE, 0.26 * n_f15 + 1.9)

# ------------------------------------------------------------- KEGG pieces ----
kegg <- read_csv(file.path(root, "results", "network_tox",
                           "enrichment_kegg.csv"), show_col_types = FALSE) %>%
  mutate(nlp = -log10(pmax(adj_p_value, 1e-300)),
         term_wrap = vapply(term, function(t)
           paste(strwrap(t, 32), collapse = "\n"), character(1)))

kegg_dot <- function(n_terms) {
  d <- kegg %>% slice_head(n = n_terms)
  ggplot(d, aes(nlp, reorder(term_wrap, nlp))) +
    geom_point(aes(size = n_overlap, colour = nlp), alpha = 0.85) +
    scale_colour_gradient(low = ACCENT, high = SIGNAL,
                          name = expression(-log[10]*P[adj]),
                          guide = guide_colourbar(barwidth = 1.1,
                                                  barheight = 2.2)) +
    scale_size_continuous(name = "Bridged genes\nin pathway",
                          range = c(1.2, 4.2), breaks = c(5, 15, 40, 80)) +
    scale_x_continuous(expand = expansion(mult = c(0, 0.10))) +
    labs(x = expression(-log[10]*P[adj]), y = NULL,
         title = paste0("KEGG pathway enrichment (top ", n_terms,
                        ", Enrichr BH-corrected)")) +
    theme_pub() +
    theme(axis.text.y = element_text(size = 6.5),
          axis.ticks.y = element_blank(), axis.line.y = element_blank(),
          panel.grid.major.y = element_blank())
}

# B2: standalone dot plot
save_fig(kegg_dot(15), file.path(ALT, "B2_kegg_dotplot_standalone.png"),
         W_15, 3.9)

# B1: Figure 4 triptych + dot plot row
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
  labs(x = "Similarity score", y = NULL, title = "Predicted targets\n(ChEMBL similarity)") +
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

fig_b1 <- (p1 | p2 | p3) / kegg_dot(12) +
  plot_layout(heights = c(1.0, 1.45)) +
  plot_annotation(caption = paste("Top: predicted targets, PPI hub genes and GO-BP",
                                  "enrichment of the bridged network. Bottom: KEGG pathways",
                                  "of bridged genes; bubble size = bridged genes in pathway,",
                                  "colour = adjusted p.")) &
  theme(plot.caption = element_text(size = 6.5, colour = MUTED, hjust = 0,
                                    margin = margin(t = 5)))
save_fig(fig_b1, file.path(ALT, "B1_fig4_with_kegg_dot.png"),
         W_DOUBLE, 3.35 + 3.3)

cat("DONE\n")
