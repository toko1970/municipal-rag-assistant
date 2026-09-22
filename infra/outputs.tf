output "workload_identity_provider" {
  description = "Use this provider name in google-github-actions/auth."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "Service account used by the GitHub deployment job."
  value       = google_service_account.github_deployer.email
}
