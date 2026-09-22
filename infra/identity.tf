locals {
  deployer_email  = google_service_account.github_deployer.email
  deployer_member = "serviceAccount:${local.deployer_email}"
}

# GitHub Actions receives short-lived Google credentials through OIDC.
resource "google_project_service" "sts" {
  project            = var.project_id
  service            = "sts.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam_credentials" {
  project            = var.project_id
  service            = "iamcredentials.googleapis.com"
  disable_on_destroy = false
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.sts]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "municipal-rag"
  display_name                       = "Municipal RAG GitHub"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository_owner == 'toko1970' && assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "github_deployer" {
  project      = var.project_id
  account_id   = "municipal-rag-deployer"
  display_name = "Municipal RAG GitHub deployer"
}

resource "google_service_account_iam_member" "github_impersonation" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
  depends_on         = [google_project_service.iam_credentials]
}

# Deployment updates the existing Cloud Run service; it does not manage its
# public access policy or read the Gemini API secret value.
resource "google_project_iam_member" "run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = local.deployer_member
}

resource "google_artifact_registry_repository_iam_member" "image_writer" {
  project    = var.project_id
  location   = var.region
  repository = "municipal-rag-images"
  role       = "roles/artifactregistry.writer"
  member     = local.deployer_member
}

resource "google_service_account_iam_member" "runtime_service_account_user" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/municipal-rag-runtime@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = local.deployer_member
}
