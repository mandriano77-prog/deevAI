# DeevAI — AWS production infrastructure

Terraform 1.6+ skeleton for the production deployment.
**Not yet applied.** Run `terraform plan` first and review carefully.

## What's provisioned

- VPC (3 AZ, public + private subnets, NAT gateway)
- RDS Postgres 16 (Multi-AZ in prod)
- KMS customer-managed key for tenant secrets (refresh tokens cifrati)
- ECS Fargate cluster (task definition + service left as TODO — see notes)
- Security groups for ALB ↔ API ↔ RDS

## Prerequisites

1. AWS account with admin IAM user
2. AWS CLI configured (`aws configure`)
3. Terraform >= 1.6
4. (one-time) S3 bucket + DynamoDB table for remote state — see commented block in `main.tf`

## First-time setup

```bash
cd infra/terraform
terraform init
terraform plan -var-file=production.tfvars
# Review the plan
terraform apply -var-file=production.tfvars
```

Read carefully before `apply`. The plan will provision real billed resources.

## Outputs

After apply you get:

- `vpc_id` — to use in any additional resources
- `rds_endpoint` — Postgres connection endpoint
- `kms_key_arn` — set as KMS_KEY_ID env in the API
- `ecs_cluster_name` — for ECS deployment

## What's NOT in this skeleton (add when needed)

- WAF for the ALB
- CloudWatch dashboards + SNS alerting
- GuardDuty
- Multi-region failover
- VPC peering / Transit Gateway
- ECS task definition (depends on container image hosting choice — see below)

## ECS task definition — next step

Once you've chosen where to host the container image (ECR recommended), add
a file `ecs.tf` with:

- `aws_ecr_repository.api`
- `aws_ecs_task_definition.api` (referencing the image)
- `aws_ecs_service.api` (running on Fargate, attached to ALB target group)
- `aws_lb_target_group.api`
- `aws_lb_listener_rule.api`

For a quick path to production without ECS, use Render (see `../../render.yaml`)
— it's a fully managed alternative at ~$25/month vs ~$80/month for the
minimal AWS stack.
