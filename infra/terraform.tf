terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  backend "gcs" {
    bucket = "municipal-rag-portfolio-tfstate-280649014820"
    prefix = "github-deploy/terraform"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
