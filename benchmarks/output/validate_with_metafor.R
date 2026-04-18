# Validate LEC meta-analysis against R metafor
# Run this script in R to verify numerical equivalence

library(metafor)

# Study data from LEC extraction
data <- data.frame(
  study = c("NCT:02551094", "NCT:03048825", "NCT:01551094", "NCT:03874338", "PMID:30578418", "NCT:03161119", "NCT:04322682", "PMID:31969186"),
  yi = c(-0.261365, -0.371064, -1.108663, -0.430783, -0.18633, -0.328504, -0.198451, -0.430783),
  sei = c(0.118843, 0.097477, 0.309253, 0.273878, 0.086911, 0.20687, 0.140516, 0.467495)
)

cat("\n=== R metafor Results ===\n")

# Random-effects meta-analysis (REML)
res <- rma(yi = yi, sei = sei, data = data, method = "REML")
print(res)

# Prediction interval
pred <- predict(res, transf = exp)
cat("\nPrediction interval (exp scale):\n")
print(pred)

# Forest plot
forest(res, transf = exp, header = TRUE,
       xlab = "Hazard Ratio", refline = 1)

# HKSJ adjustment
res_hksj <- rma(yi = yi, sei = sei, data = data, method = "REML", test = "knha")
cat("\n=== HKSJ-adjusted Results ===\n")
print(res_hksj)

# LEC comparison values
cat("\n=== LEC Results for Comparison ===\n")
cat("Pooled (log scale):", -0.309791, "\n")
cat("Pooled (exp scale):", 0.7336, "\n")
cat("CI low:", 0.6455, "\n")
cat("CI high:", 0.8339, "\n")
cat("SE:", 0.0653, "\n")
cat("I2:", 29.96, "%\n")
cat("tau2:", 0.009338, "\n")
cat("Q:", 9.9943, "\n")

# Tolerance check
tol <- 0.02
lec_pooled <- 0.7336
metafor_pooled <- exp(res$beta)

if (abs(lec_pooled - metafor_pooled) < tol) {
  cat("\n[PASS] Pooled estimates match within tolerance\n")
} else {
  cat("\n[WARN] Pooled estimates differ by:", abs(lec_pooled - metafor_pooled), "\n")
}

# Egger's test
cat("\n=== Publication Bias Tests ===\n")
regtest(res)

# Trim and fill
tf <- trimfill(res)
cat("\nTrim and fill:\n")
print(tf)
funnel(tf)

cat("\n=== Benchmark Complete ===\n")
