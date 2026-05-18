## ───────────────────────────────────────────────────────────────
## deevAI — AWS production infrastructure (Terraform skeleton)
##
## What this provisions:
##   - VPC (3 AZ, public + private subnets)
##   - RDS Postgres 16 (Multi-AZ in prod, single-AZ in staging)
##   - KMS customer-managed key for tenant secrets (refresh tokens)
##   - Secrets Manager for the app's own secrets
##   - ECS Fargate cluster for the FastAPI backend
##   - ALB with HTTPS via ACM
##   - Route 53 records for api.deevai.app
##   - IAM roles + policies (least-privilege)
##
## Not in this skeleton (deliberately, add later):
##   - WAF
##   - CloudWatch dashboards
##   - SNS alerting
##   - GuardDuty
##   - Multi-region failover
##
## To apply:
##   cd infra/terraform
##   terraform init
##   terraform plan -var-file=production.tfvars
##   terraform apply -var-file=production.tfvars
## ───────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Remote state on S3 — configure backend bucket once outside Terraform
  # (manual one-time setup, so the backend itself doesn't depend on the apply).
  # backend "s3" {
  #   bucket         = "deevai-tf-state"
  #   key            = "production/terraform.tfstate"
  #   region         = "eu-central-1"
  #   dynamodb_table = "deevai-tf-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "deevAI"
      Env       = var.env
      ManagedBy = "Terraform"
    }
  }
}

# ── VPC ──────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "deevai-${var.env}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.region}a", "${var.region}b", "${var.region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = var.env != "production"
  enable_dns_hostnames = true
  enable_dns_support   = true
}

# ── KMS key for tenant secrets ──────────────────────────────────
resource "aws_kms_key" "tenant_secrets" {
  description             = "Encrypts tenant refresh_tokens and client_secrets at rest"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableIAM"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "tenant_secrets" {
  name          = "alias/deevai-${var.env}-tenant-secrets"
  target_key_id = aws_kms_key.tenant_secrets.key_id
}

data "aws_caller_identity" "current" {}

# ── RDS Postgres ────────────────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  name       = "deevai-${var.env}-db"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name   = "deevai-${var.env}-rds"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main" {
  identifier               = "deevai-${var.env}"
  engine                   = "postgres"
  engine_version           = "16.3"
  instance_class           = var.env == "production" ? "db.t4g.small" : "db.t4g.micro"
  allocated_storage        = 20
  max_allocated_storage    = 100
  storage_encrypted        = true
  db_name                  = "deevai"
  username                 = "deevai"
  manage_master_user_password = true
  db_subnet_group_name     = aws_db_subnet_group.main.name
  vpc_security_group_ids   = [aws_security_group.rds.id]
  multi_az                 = var.env == "production"
  backup_retention_period  = 7
  deletion_protection      = var.env == "production"
  skip_final_snapshot      = var.env != "production"
  apply_immediately        = true
}

# ── ECS Cluster + Service for the FastAPI backend ───────────────
resource "aws_ecs_cluster" "main" {
  name = "deevai-${var.env}"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_security_group" "api" {
  name   = "deevai-${var.env}-api"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "alb" {
  name   = "deevai-${var.env}-alb"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# The ECS task definition + service + ALB rules are intentionally
# left as outputs/placeholders here — see infra/terraform/ecs.tf to flesh out
# once you've decided container image hosting (ECR vs Docker Hub).

output "vpc_id" { value = module.vpc.vpc_id }
output "rds_endpoint" { value = aws_db_instance.main.endpoint }
output "kms_key_arn" { value = aws_kms_key.tenant_secrets.arn }
output "ecs_cluster_name" { value = aws_ecs_cluster.main.name }
