variable "region" {
  description = "AWS region — EU for GDPR data residency"
  type        = string
  default     = "eu-central-1"
}

variable "env" {
  description = "Deployment environment"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "staging", "dev"], var.env)
    error_message = "env must be one of: production, staging, dev"
  }
}

variable "domain_name" {
  description = "Public domain — api.deevai.app, deevai.app"
  type        = string
  default     = "deevai.app"
}
