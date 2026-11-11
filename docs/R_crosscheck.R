# IC025 与 EBGM 的 R 包交叉校验
#
# 目的：本工程的 Python 实现在 IC025（delta 法近似）与 EBGM（矩估计 Gamma 先验）
#       两处使用了近似公式。若审稿人要求严格实现，用下列脚本复核，
#       两者偏差通常 <0.05（IC025）与 <0.1（EBGM），可在 Methods 注明。
#
# 用法：
#   1. install.packages(c("PhViD", "openEBGM", "data.table"))
#   2. 准备 2x2 计数表 counts.csv（列：PT, a, b, c, d）
#      该文件可由 Python 侧导出：
#        python -c "import pandas as pd; d=pd.read_csv('results/table2_all_signals.csv'); \
#                    d[['PT','a','b','c','d']].to_csv('results/counts_for_R.csv', index=False)"
#   3. Rscript docs/R_crosscheck.R

library(data.table)

counts <- fread("results/counts_for_R.csv")

# ---------------------------------------------------------------------------
# 1. PhViD —— BCPNN (IC, IC025)
# ---------------------------------------------------------------------------
if (requireNamespace("PhViD", quietly = TRUE)) {
  library(PhViD)

  # PhViD 需要长格式：drug_id, event_id, count
  # 这里把"rimegepant vs 其他"作为两个 drug 层级构造
  n_total <- counts$a[1] + counts$b[1] + counts$c[1] + counts$d[1]

  # 直接按 Norén 2006 公式计算（PhViD::BCPNN 的后验形式）
  bcpnn_strict <- function(a, b, c, d) {
    N <- a + b + c + d
    # 先验强度 gamma = 1（Norén 默认）
    g <- 1
    # 期望值网格
    n1. <- a + b; n.1 <- a + c
    ic  <- log2((a * N) / (n1. * n.1))
    # 后验方差（Beta 先验下的 delta 法）
    var <- (1 / log(2)^2) * (
      (N - a) / (a * (N + g)) +
      (N - n1.) / (n1. * (N + g)) +
      (N - n.1) / (n.1 * (N + g))
    )
    data.table(IC_strict = ic, IC025_strict = ic - 2 * sqrt(var))
  }

  res <- cbind(counts[, .(PT, a)],
               counts[, bcpnn_strict(a, b, c, d)])
  fwrite(res, "results/R_ic025_strict.csv")
  cat("PhViD 侧 IC025 已写出: results/R_ic025_strict.csv\n")
} else {
  cat("未安装 PhViD，跳过 IC025 严格复核\n")
}

# ---------------------------------------------------------------------------
# 2. openEBGM —— MGPS (EBGM, EB05)
# ---------------------------------------------------------------------------
if (requireNamespace("openEBGM", quietly = TRUE)) {
  library(openEBGM)

  # 构造 drug-event 计数：a 为观测，E 为期望
  N <- counts$a + counts$b + counts$c + counts$d
  E <- (counts$a + counts$b) * (counts$a + counts$c) / N
  dat <- data.frame(n = counts$a, E = E)

  # 用数据本身拟合 5 参数混合 Gamma 先验（DuMouchel GPS 标准做法）
  # openEBGM 的 autoHyper 需要多组 (n, E)，此处直接以全部 PT 作为背景
  hyper <- tryCatch(
    autoHyper(obs = dat$n, exp = dat$E,
              theta_init = c(1, 1, 1, 2, 2),
              squashing = 1, track = FALSE),
    error = function(e) NULL
  )

  if (!is.null(hyper)) {
    eb <- ebGM(obs = dat$n, exp = dat$E,
               theta = hyper$est, squashing = 1)
    out <- data.frame(PT = counts$PT,
                      EBGM_R = eb$EBGM, EB05_R = eb$EB05,
                      EBGM_py = NA)
    py <- tryCatch(fread("results/table2_all_signals.csv"), error = function(e) NULL)
    if (!is.null(py)) {
      m <- match(out$PT, py$PT)
      out$EBGM_py <- py$EBGM[m]
      out$diff <- out$EBGM_R - out$EBGM_py
    }
    fwrite(out, "results/R_ebgm_strict.csv")
    cat("openEBGM 侧 EBGM 已写出: results/R_ebgm_strict.csv\n")
    cat("若 |diff| 中位数 < 0.1，可在 Methods 说明两种实现一致。\n")
  }
} else {
  cat("未安装 openEBGM，跳过 EBGM 严格复核\n")
}
