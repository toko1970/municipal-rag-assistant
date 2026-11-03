locals {
  cleanup_job_name        = "municipal-rag-public-api-cleanup"
  cleanup_db_url_secret   = "rag-database-url"
  project_number          = data.google_project.current.number
  scheduler_service_agent = "service-${local.project_number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudscheduler" {
  project            = var.project_id
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "monitoring" {
  project            = var.project_id
  service            = "monitoring.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "public_api_cleanup" {
  project      = var.project_id
  account_id   = "municipal-rag-cleanup"
  display_name = "Municipal RAG anonymous state cleanup"
}

resource "google_project_iam_member" "cleanup_cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.public_api_cleanup.email}"
}

resource "google_secret_manager_secret_iam_member" "cleanup_database_url" {
  project   = var.project_id
  secret_id = local.cleanup_db_url_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.public_api_cleanup.email}"
}

resource "google_cloud_run_v2_job" "public_api_cleanup" {
  name                = local.cleanup_job_name
  project             = var.project_id
  location            = var.region
  deletion_protection = true

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.public_api_cleanup.email
      max_retries     = 1
      timeout         = "3600s"

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.rag.connection_name]
        }
      }

      containers {
        image   = var.public_api_cleanup_image
        command = ["python"]
        args    = ["-m", "scripts.cleanup_public_api_state"]

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = local.cleanup_db_url_secret
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_secret_manager_secret_iam_member.cleanup_database_url,
    google_project_iam_member.cleanup_cloud_sql_client,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.public_api_cleanup.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.public_api_scheduler.email}"
}

resource "google_service_account" "public_api_scheduler" {
  project      = var.project_id
  account_id   = "municipal-rag-scheduler"
  display_name = "Municipal RAG cleanup Scheduler caller"
}

resource "google_service_account_iam_member" "scheduler_service_agent_token_creator" {
  service_account_id = google_service_account.public_api_scheduler.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${local.scheduler_service_agent}"

  depends_on = [google_project_service.cloudscheduler]
}

resource "google_cloud_scheduler_job" "public_api_cleanup" {
  name             = "municipal-rag-public-api-cleanup-hourly"
  project          = var.project_id
  region           = var.region
  description      = "Delete only expired anonymous idempotency and quota HMAC rows."
  schedule         = "0 * * * *"
  time_zone        = "Asia/Tokyo"
  paused           = !var.enable_public_api_cleanup_schedule
  attempt_deadline = "3600s"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.public_api_cleanup.name}:run"
    body        = base64encode("{}")
    headers = {
      "Content-Type" = "application/json"
    }

    oauth_token {
      service_account_email = google_service_account.public_api_scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  retry_config {
    retry_count = 2
  }

  depends_on = [
    google_project_service.cloudscheduler,
    google_service_account_iam_member.scheduler_service_agent_token_creator,
    google_cloud_run_v2_job_iam_member.scheduler_invoker,
  ]

  lifecycle {
    precondition {
      condition = !var.enable_public_api_cleanup_schedule || (
        var.public_api_cleanup_notification_channel != ""
      )
      error_message = "A Monitoring notification channel is required before enabling cleanup scheduling."
    }
  }
}

resource "google_monitoring_alert_policy" "public_api_cleanup_failed" {
  count = var.enable_public_api_cleanup_schedule ? 1 : 0

  depends_on = [google_project_service.monitoring]

  project               = var.project_id
  display_name          = "Municipal RAG anonymous cleanup failed"
  combiner              = "OR"
  notification_channels = [var.public_api_cleanup_notification_channel]
  enabled               = true

  conditions {
    display_name = "Cloud Run cleanup job has a failed execution"

    condition_threshold {
      filter          = <<-EOT
        metric.type = "run.googleapis.com/job/completed_execution_count"
        AND resource.type = "cloud_run_job"
        AND resource.labels.job_name = "${local.cleanup_job_name}"
        AND metric.labels.result = "failed"
      EOT
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      trigger {
        count = 1
      }
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "The anonymous-state cleanup job failed. Inspect the Cloud Run Job execution logs and rerun only after resolving the cause."
  }
}

resource "google_monitoring_alert_policy" "public_api_cleanup_missing" {
  count = var.enable_public_api_cleanup_schedule ? 1 : 0

  depends_on = [google_project_service.monitoring]

  project               = var.project_id
  display_name          = "Municipal RAG anonymous cleanup has not run"
  combiner              = "OR"
  notification_channels = [var.public_api_cleanup_notification_channel]
  enabled               = true

  conditions {
    display_name = "No Cloud Run cleanup job completion in two hours"

    condition_absent {
      filter   = <<-EOT
        metric.type = "run.googleapis.com/job/completed_execution_count"
        AND resource.type = "cloud_run_job"
        AND resource.labels.job_name = "${local.cleanup_job_name}"
      EOT
      duration = "7200s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "The hourly anonymous-state cleanup job has produced no completion metric in two hours. Check the Cloud Scheduler job, its IAM/OAuth configuration, and Cloud Run Job executions."
  }
}
