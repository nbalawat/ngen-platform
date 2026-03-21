# Dev Environment — NGEN Platform
# Provisions a minimal development environment on AWS.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

variable "vpc_id" {
  description = "VPC ID for deployment"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for services"
  type        = list(string)
}

variable "db_subnet_group" {
  description = "DB subnet group name"
  type        = string
}

variable "security_group_ids" {
  description = "Security group IDs"
  type        = list(string)
}

# EKS Cluster
module "eks" {
  source = "../../modules/eks"

  cluster_name        = "ngen-dev"
  cluster_version     = "1.29"
  vpc_id              = var.vpc_id
  subnet_ids          = var.subnet_ids
  node_instance_types = ["t3.large"]
  node_desired_size   = 2
  node_min_size       = 1
  node_max_size       = 5

  tags = {
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# RDS PostgreSQL
module "rds" {
  source = "../../modules/rds"

  identifier             = "ngen-dev-postgres"
  instance_class         = "db.t3.micro"
  allocated_storage      = 10
  vpc_security_group_ids = var.security_group_ids
  subnet_group_name      = var.db_subnet_group

  tags = {
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# ElastiCache Redis
module "redis" {
  source = "../../modules/elasticache"

  cluster_id         = "ngen-dev-redis"
  node_type          = "cache.t3.micro"
  security_group_ids = var.security_group_ids
  subnet_group_name  = var.db_subnet_group

  tags = {
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

output "eks_endpoint" {
  value = module.eks.cluster_endpoint
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "redis_endpoint" {
  value = module.redis.endpoint
}
