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
