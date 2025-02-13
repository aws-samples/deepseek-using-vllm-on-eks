# Hosting DeepSeek-R1 on Amazon EKS

In this tutorial, we’ll walk you through how to host [**DeepSeek-R1**](https://github.com/deepseek-ai/DeepSeek-R1) model on AWS using **Amazon EKS**. We are using [**Amazon EKS Auto Mode**](https://aws.amazon.com/eks/auto-mode/?trk=309fae93-0dac-4940-8d50-5b585d53959f&sc_channel=el) for the the flexibility and scalability that it provides, while eliminating the need for you to manage the Kubernetes control plane, compute, storage, and networking components.

## Deploying DeepSeek-R1 on Amazon EKS Auto Mode

For this tutorial, we’ll use the [***DeepSeek-R1-Distill-Llama-8B***](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B) distilled model. 
While it requires fewer resources (like GPU) compared to the full [***DeepSeek-R1***](https://huggingface.co/deepseek-ai/DeepSeek-R1) model with 671B parameters, it provides a lighter, though less powerful, option compared to the full model. 

If you'd prefer to deploy the full DeepSeek-R1 model, simply replace the distilled model in the vLLM configuration.

###  PreReqs

- [Check AWS Instance Quota](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html)
- [Install kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Install terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli)
- [Install finch](https://runfinch.com/docs/getting-started/installation/) or [docker](https://docs.docker.com/get-started/get-docker/) 

### Create an Amazon  EKS Cluster w/ Auto Mode using Terraform
We'll use Terraform to easily provision the infrastructure, including a VPC, ECR repository, and an EKS cluster with Auto Mode enabled.

``` bash
# Clone the GitHub repo with the manifests
git clone https://github.com/aws-samples/deepseek-using-vllm-on-eks
cd deepseek-using-vllm-on-eks

# Apply the Terraform configuration
terraform init
terraform apply -auto-approve

$(terraform output configure_kubectl | jq -r)
```

### Deploy  DeepSeek Model

In this step, we will deploy the **DeepSeek-R1-Distill-Llama-8B** model using vLLM on Amazon EKS. 
We will walk through deploying the model with the option to enable GPU-based, Neuron-based (Inferentia and Trainium), 
or both, by configuring the parameters accordingly.

#### Configuring Node Pools
The `enable_auto_mode_node_pool` parameter can be set to `true` to automatically create node pools when using EKS AutoMode. 
This configuration is defined in the [nodepool_automode.tf](./nodepool_automode.tf) file. If you're using EKS AutoMode, this will ensure that the appropriate node pools are provisioned.

#### Customizing Helm Chart Values
To customize the values used to host your model using vLLM, check the [helm.tf](./helm.tf) file. 
This file defines the model to be deployed (**deepseek-ai/DeepSeek-R1-Distill-Llama-8B**) and allows you to pass additional parameters to vLLM. 
You can modify this file to change resource configurations, node selectors, or tolerations as needed.

``` bash
# Let's start by just enabling the GPU based option:
terraform apply -auto-approve -var="enable_deep_seek_gpu=true" -var="enable_auto_mode_node_pool=true"

# Check the pods in the 'deepseek' namespace 
kubectl get po -n deepseek
```

<details>
  <summary>Click to deploy with Neuron based Instances</summary>

  ``` bash
  # Before Adding Neuron support we need to build the image for the vllm deepseek neuron based deployment.
  
  # Let's start by getting the ECR repo name where we'll be pushing the image
  export ECR_REPO_NEURON=$(terraform output ecr_repository_uri_neuron | jq -r)

  # Now, let's clone the official vLLM repo and use its official container image with the neuron drivers installed
  git clone https://github.com/vllm-project/vllm
  cd vllm

  # Building image
  finch build --platform linux/amd64 -f Dockerfile.neuron -t $ECR_REPO_NEURON:0.1 .

  # Login on ECR repository
  aws ecr get-login-password | finch login --username AWS --password-stdin $ECR_REPO_NEURON

  # Pushing the image
  finch push $ECR_REPO_NEURON:0.1

  # Remove vllm repo and container image from local machine
  cd ..
  rm -rf vllm
  finch rmi $ECR_REPO_NEURON:0.1

  # Enable additional nodepool and deploy vLLM DeepSeek model
  terraform apply -auto-approve -var="enable_deep_seek_gpu=true" -var="enable_deep_seek_neuron=true" -var="enable_auto_mode_node_pool=true"
  ```
</details>

Initially, the pod might be in a **Pending state** while EKS Auto Mode provisions the underlying EC2 instances with the required drivers.

<details>
  <summary>Click if your pod is stuck in a "pending" state for several minutes</summary>
   
  ``` bash
  # Check if the node was provisioned
  kubectl get nodes -l owner=data-engineer
  ```
  If no nodes are displayed, verify that your AWS account has sufficient service quota to launch the required instances.
  Check the quota limits for G, P, or Inf instances (e.g., GPU or Neuron based instances).
  
  For more information, refer to the [AWS EC2 Instance Quotas documentation](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html).

  **Note:** Those quotas are based on vCPUs, not the number of instances, so be sure to request accordingly.

</details>

``` bash
# Wait for the pod to reach the 'Running' state
kubectl get po -n deepseek --watch

# Verify that a new Node has been created
kubectl get nodes -l owner=data-engineer -o wide

# Check the logs to confirm that vLLM has started 
# Select the command based on the accelerator you choose to deploy.
kubectl logs deployment.apps/deepseek-gpu-vllm-chart -n deepseek
kubectl logs deployment.apps/deepseek-neuron-vllm-chart -n deepseek
```

You should see the log entry **Application startup complete** once the deployment is ready.

### Interact with the LLM

Next, we can create a local proxy to interact with the model using a curl request.

``` bash
# Set up a proxy to forward the service port to your local terminal
# We are exposing Neuron based on port 8080 and GPU based on port 8081
kubectl port-forward svc/deepseek-neuron-vllm-chart -n deepseek 8080:80 > port-forward-neuron.log 2>&1 &
kubectl port-forward svc/deepseek-gpu-vllm-chart -n deepseek 8081:80 > port-forward-gpu.log 2>&1 &

# Send a curl request to the model (change the port according to the accelerator you are using)
curl -X POST "http://localhost:8080/v1/chat/completions" -H "Content-Type: application/json" --data '{
 "model": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
 "messages": [
 {
 "role": "user",
 "content": "What is Kubernetes?"
 }
 ]
 }'
```
The response may take a few seconds to build, depending on the complexity of the model’s output. 
You can monitor the progress via the `deepseek-gpu-vllm-chart` or `deepseek-neuron-vllm-chart` deployment logs.

### Build a Chatbot UI for the Model

While direct API requests work fine, let’s build a more user-friendly Chatbot UI to interact with the model. The source code for the UI is already available in the GitHub repository.

``` bash
# Retrieve the ECR repository URI created by Terraform
export ECR_REPO=$(terraform output ecr_repository_uri | jq -r)

# Build the container image for the Chatbot UI
finch build --platform linux/amd64 -t $ECR_REPO:0.1 chatbot-ui/application/.

# Login to ECR and push the image
aws ecr get-login-password | finch login --username AWS --password-stdin $ECR_REPO
finch push $ECR_REPO:0.1

# Update the deployment manifest to use the image
sed -i "s#__IMAGE_DEEPSEEK_CHATBOT__#$ECR_REPO:0.1#g" chatbot-ui/manifests/deployment.yaml

# Generate a random password for the Chatbot UI login
sed -i "s|__PASSWORD__|$(openssl rand -base64 12 | tr -dc A-Za-z0-9 | head -c 16)|" chatbot-ui/manifests/deployment.yaml

# Deploy the UI and create the ingress class required for load balancers
kubectl apply -f chatbot-ui/manifests/ingress-class.yaml
kubectl apply -f chatbot-ui/manifests/deployment.yaml

# Get the URL for the load balancer to access the application
echo http://$(kubectl get ingress/deepseek-chatbot-ingress -n deepseek -o json | jq -r '.status.loadBalancer.ingress[0].hostname')
```

To access the Chatbot UI, you'll need the username and password stored in a Kubernetes secret.

``` bash
echo -e "Username=$(kubectl get secret deepseek-chatbot-secrets -n deepseek -o jsonpath='{.data.admin-username}' | base64 --decode)\nPassword=$(kubectl get secret deepseek-chatbot-secrets -n deepseek -o jsonpath='{.data.admin-password}' | base64 --decode)"
```
After logging in, you'll see a new **Chatbot tab** where you can interact with the model!
In this tab, you'll notice a dropdown menu that lets you switch between Neuron-based and GPU-based deployments!

![chatbot-ui](/static/images/chatbot.jpg)

---
### Disclaimer

**This repository is intended for demonstration and learning purposes only.**
It is **not** intended for production use. The code provided here is for educational purposes and should not be used in a live environment without proper testing, validation, and modifications.

Use at your own risk. The authors are not responsible for any issues, damages, or losses that may result from using this code in production.
