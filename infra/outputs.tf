output "workload_identity_provider" {
  description = "Use this provider name in google-github-actions/auth."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "Service account used by the GitHub deployment job."
  value       = google_service_account.github_deployer.email
}

output "cloud_sql_connection_name" {
  description = "Set this value as the GitHub production environment variable CLOUD_SQL_CONNECTION_NAME."
  value       = google_sql_database_instance.rag.connection_name
}

output "qdrant_api_key_secret" {
  description = "Add one Qdrant database API key version to this secret after creating the cluster."
  value       = google_secret_manager_secret.qdrant_api_key.secret_id
}

output "monthly_budget_name" {
  description = "Cloud Billing budget protecting the portfolio project."
  value       = google_billing_budget.rag_portfolio.name
}

output "visual_asset_bucket" {
  description = "Private bucket containing reviewed visual evidence for the public demo."
  value       = google_storage_bucket.visual_assets.name
}

output "session_signing_keys_secret" {
  description = "Register a generated JSON signing-key map as a secret version before deploying the API."
  value       = google_secret_manager_secret.session_signing_keys.secret_id
}

output "public_api_cleanup_job" {
  description = "Cloud Run Job that removes expired anonymous HMAC and quota identifiers."
  value       = google_cloud_run_v2_job.public_api_cleanup.name
}

output "public_api_cleanup_scheduler" {
  description = "Hourly cleanup Scheduler; paused unless explicitly enabled after production approval."
  value       = google_cloud_scheduler_job.public_api_cleanup.name
}
