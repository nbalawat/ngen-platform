# RDS PostgreSQL Module for NGEN Platform
# Provisions a managed PostgreSQL instance for the tenant service
# and any future services requiring relational storage.

variable "identifier" {
  description = "RDS instance identifier"
  type        = string
  default     = "ngen-postgres"
}

variable "engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "16.2"
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "ngen"
}

variable "db_username" {
  description = "Master username"
  type        = string
  default     = "ngen_admin"
}

variable "vpc_security_group_ids" {
  description = "Security group IDs"
  type        = list(string)
}

variable "subnet_group_name" {
  description = "DB subnet group name"
  type        = string
}

variable "tags" {
  description = "Tags to apply"
  type        = map(string)
  default     = {}
}

resource "aws_db_instance" "this" {
  identifier             = var.identifier
  engine                 = "postgres"
  engine_version         = var.engine_version
  instance_class         = var.instance_class
  allocated_storage      = var.allocated_storage
  db_name                = var.db_name
  username               = var.db_username
  manage_master_user_password = true
  vpc_security_group_ids = var.vpc_security_group_ids
  db_subnet_group_name   = var.subnet_group_name
  skip_final_snapshot    = true
  multi_az               = false
  storage_encrypted      = true

  tags = merge(var.tags, {
    "Platform" = "ngen"
  })
}

output "endpoint" {
  value = aws_db_instance.this.endpoint
}

output "db_name" {
  value = aws_db_instance.this.db_name
}
