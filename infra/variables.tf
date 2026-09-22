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
