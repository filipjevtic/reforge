variable "environment" {
  type = string
}

locals {
  bucket_name = "myapp-${var.environment}-data"
}
