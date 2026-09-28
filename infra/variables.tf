variable "project_id" {
  description = "Existing Google Cloud project."
  type        = string
  default     = "municipal-rag-portfolio"
}

variable "region" {
  description = "Region of the existing Cloud Run service and Artifact Registry repository."
  type        = string
  default     = "asia-northeast1"
}

variable "github_repository" {
  description = "Only this GitHub repository may impersonate the deployer service account."
  type        = string
  default     = "toko1970/municipal-rag-assistant"
}

variable "cloud_sql_instance_name" {
  description = "Cloud SQL instance used by the public RAG v2 demo."
  type        = string
  default     = "municipal-rag-postgres"
}

variable "cloud_sql_tier" {
  description = "Small, zonal Cloud SQL tier for the portfolio demo."
  type        = string
  default     = "db-f1-micro"
}

variable "billing_account_id" {
  description = "Billing account used by the municipal-rag-portfolio project."
  type        = string
  default     = "01D3CC-E463CE-291ED3"
}

variable "monthly_budget_jpy" {
  description = "Monthly alert budget for this portfolio project in JPY."
  type        = number
  default     = 2000
}

variable "visual_asset_bucket_name" {
  description = "Private bucket for reviewed visual evidence used by the public demo."
  type        = string
  default     = "municipal-rag-portfolio-visual-assets-280649014820"
}
