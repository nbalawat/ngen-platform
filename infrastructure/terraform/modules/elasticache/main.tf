# ElastiCache Redis Module for NGEN Platform
# Provisions a managed Redis cluster for rate limiting,
# policy persistence, and caching.

variable "cluster_id" {
  description = "ElastiCache cluster ID"
  type        = string
  default     = "ngen-redis"
}

variable "node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "num_cache_nodes" {
  description = "Number of cache nodes"
  type        = number
  default     = 1
}

variable "security_group_ids" {
  description = "Security group IDs"
  type        = list(string)
}

variable "subnet_group_name" {
  description = "ElastiCache subnet group name"
  type        = string
}

variable "tags" {
  description = "Tags to apply"
  type        = map(string)
  default     = {}
}

resource "aws_elasticache_cluster" "this" {
  cluster_id           = var.cluster_id
  engine               = "redis"
  node_type            = var.node_type
  num_cache_nodes      = var.num_cache_nodes
  port                 = 6379
  security_group_ids   = var.security_group_ids
  subnet_group_name    = var.subnet_group_name

  tags = merge(var.tags, {
    "Platform" = "ngen"
  })
}

output "endpoint" {
  value = aws_elasticache_cluster.this.cache_nodes[0].address
}

output "port" {
  value = aws_elasticache_cluster.this.port
}
