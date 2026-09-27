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
