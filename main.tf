locals {
  region   = "us-east-1"
  vpc_cidr = "10.0.0.0/16"
  name     = "eks-automode"
  azs      = slice(data.aws_availability_zones.available.names, 0, 3)

  tags = {
    Blueprint = local.name
  }
}


# Define the required providers
provider "aws" {
  region = local.region # Change to your desired region
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    # This requires the awscli to be installed locally where Terraform is executed
    args = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

data "aws_availability_zones" "available" {
  # Do not include local zones
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

# Use the Terraform VPC module to create a VPC
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.17.0" # Use the latest version available

  name = "${local.name}-vpc"
  cidr = local.vpc_cidr

  azs             = local.azs
  private_subnets = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 4, k)]
  public_subnets  = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 48)]

  enable_nat_gateway = true
  single_nat_gateway = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }

  tags = local.tags
}

# Use the Terraform EKS module to create an EKS cluster
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0" # Use the latest version available

  cluster_name    = local.name
  cluster_version = "1.31" # Specify the EKS version you want to use
  
  cluster_endpoint_public_access           = true
  enable_irsa                              = true
  enable_cluster_creator_admin_permissions = true

  cluster_compute_config = {
    enabled    = true
    node_pools = ["general-purpose"]
  }


    vpc_id     = module.vpc.vpc_id
    subnet_ids = module.vpc.private_subnets

    tags = local.tags
  }


resource "aws_ecr_repository" "deepseek-ecr" {
  name                 = "${local.name}-deepseek-ecr"
  image_tag_mutability = "MUTABLE"
}

# Outputs
output "configure_kubectl" {
  description = "Configure kubectl: make sure you're logged in with the correct AWS profile and run the following command to update your kubeconfig"
  value       = "aws eks --region ${local.region} update-kubeconfig --name ${module.eks.cluster_name}"
}

output "ecr_repository_uri" {
  value = aws_ecr_repository.deepseek-ecr.repository_url
}
