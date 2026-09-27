locals {
  runtime_service_account_email = "municipal-rag-runtime@${var.project_id}.iam.gserviceaccount.com"
  runtime_member                = "serviceAccount:${local.runtime_service_account_email}"
  database_name                 = "rag_portfolio"
  database_user                 = "rag_app"
}

resource "google_project_service" "sqladmin" {
  project            = var.project_id
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_sql_database_instance" "rag" {
  name                = var.cloud_sql_instance_name
  project             = var.project_id
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = true

  settings {
    tier              = var.cloud_sql_tier
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"
    disk_type         = "PD_HDD"
    disk_size         = 10
    disk_autoresize   = false

    backup_configuration {
      enabled = false
    }

    ip_configuration {
      ipv4_enabled = true
    }
  }

  depends_on = [google_project_service.sqladmin]
}

resource "google_sql_database" "rag" {
  name     = local.database_name
  project  = var.project_id
  instance = google_sql_database_instance.rag.name
}

resource "random_password" "database" {
  length  = 32
  special = false
}

resource "google_sql_user" "rag" {
  name     = local.database_user
  project  = var.project_id
  instance = google_sql_database_instance.rag.name
  password = random_password.database.result
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "rag-database-url"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  secret_data = format(
    "postgresql+psycopg://%s:%s@/%s?host=/cloudsql/%s",
    local.database_user,
    random_password.database.result,
    local.database_name,
    google_sql_database_instance.rag.connection_name,
  )
}

resource "google_secret_manager_secret" "qdrant_api_key" {
  secret_id = "qdrant-api-key"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_project_iam_member" "runtime_cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = local.runtime_member
}

resource "google_secret_manager_secret_iam_member" "runtime_database_url" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.runtime_member
}

resource "google_secret_manager_secret_iam_member" "runtime_qdrant_api_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.qdrant_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.runtime_member
}
