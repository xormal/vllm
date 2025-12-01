# vLLM Build Guide for Ubuntu 24.04 LTS with NVIDIA GPU

## Document Purpose

This is a **complete, step-by-step guide** for building vLLM from source on a **fresh Ubuntu 24.04 LTS** system with **NVIDIA GPU support**. This guide assumes you're starting with a minimal/clean Ubuntu installation.

**Target System**: Ubuntu 24.04 LTS (Noble Numbat)
**GPU Support**: NVIDIA CUDA
**Build Time**: ~30-60 minutes (depending on system specs)

---

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Step 1: System Update & Essential Tools](#step-1-system-update--essential-tools)
3. [Step 2: NVIDIA Driver Installation](#step-2-nvidia-driver-installation)
4. [Step 3: CUDA Toolkit Installation](#step-3-cuda-toolkit-installation)
5. [Step 4: Python Environment Setup](#step-4-python-environment-setup)
6. [Step 5: Build Dependencies](#step-5-build-dependencies)
7. [Step 6: Clone vLLM Repository](#step-6-clone-vllm-repository)
8. [Step 7: Build vLLM](#step-7-build-vllm)
9. [Step 8: Install vLLM](#step-8-install-vllm)
10. [Step 9: Verification & Testing](#step-9-verification--testing)
11. [Troubleshooting](#troubleshooting)
12. [Performance Tuning](#performance-tuning)
13. [Uninstallation](#uninstallation)

---

## System Requirements

### Minimum Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS (fresh install) |
| **GPU** | NVIDIA GPU with Compute Capability 7.0+ | Compute Capability 8.0+ (A100, H100, RTX 30xx/40xx) |
| **GPU Memory** | 8 GB VRAM | 16+ GB VRAM |
| **System RAM** | 16 GB | 32+ GB |
| **Disk Space** | 50 GB free | 100+ GB free (for models) |
| **CPU** | 8 cores | 16+ cores |
| **CUDA** | 12.1+ | 12.4+ |
| **Python** | 3.10, 3.11, 3.12, or 3.13 | 3.12 |

### Check Your GPU

```bash
# Check if NVIDIA GPU is detected
lspci | grep -i nvidia

# Expected output (example):
# 01:00.0 VGA compatible controller: NVIDIA Corporation ...
```

If you don't see any output, ensure your NVIDIA GPU is properly installed in your system.

---

## Step 1: System Update & Essential Tools

### 1.1 Update System

```bash
# Update package lists
sudo apt update

# Upgrade existing packages
sudo apt upgrade -y

# Install essential build tools
sudo apt install -y \
    build-essential \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    curl \
    wget \
    gnupg \
    lsb-release \
    git \
    vim \
    htop
```

**Time**: ~5-10 minutes

### 1.2 Verify System Information

```bash
# Check Ubuntu version
lsb_release -a

# Expected output:
# Description:    Ubuntu 24.04 LTS
# Release:        24.04
# Codename:       noble

# Check kernel version
uname -r

# Expected: 6.8.x or higher
```

---

## Step 2: NVIDIA Driver Installation

### 2.1 Remove Old NVIDIA Drivers (if any)

```bash
# Remove any existing NVIDIA drivers
sudo apt purge -y nvidia* libnvidia*

# Clean up
sudo apt autoremove -y
sudo apt autoclean
```

### 2.2 Add NVIDIA Driver PPA

Ubuntu 24.04 includes NVIDIA drivers in the official repositories, but we'll use the latest:

```bash
# Add graphics drivers PPA (for latest drivers)
sudo add-apt-repository ppa:graphics-drivers/ppa -y

# Update package list
sudo apt update
```

### 2.3 Find Recommended Driver

```bash
# Check recommended driver
ubuntu-drivers devices

# Expected output:
# ...
# recommended: nvidia-driver-550
# or similar (driver version 525+)
```

### 2.4 Install NVIDIA Driver

**Option A: Install Recommended Driver (Easiest)**

```bash
# Install recommended driver automatically
sudo ubuntu-drivers install

# Or install specific version
sudo apt install -y nvidia-driver-550

# For server systems (no GUI needed), use server variant:
sudo apt install -y nvidia-driver-550-server
```

**Option B: Install Latest Driver Manually**

```bash
# As of 2025, driver 550+ is recommended
sudo apt install -y \
    nvidia-driver-550 \
    nvidia-dkms-550 \
    nvidia-utils-550
```

**Time**: ~5-10 minutes

### 2.5 Reboot System

```bash
# Reboot to load NVIDIA driver
sudo reboot
```

**IMPORTANT**: You must reboot after installing NVIDIA drivers.

### 2.6 Verify Driver Installation

After reboot:

```bash
# Check NVIDIA driver
nvidia-smi

# Expected output:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 550.xx       Driver Version: 550.xx       CUDA Version: 12.4     |
# |-------------------------------+----------------------+----------------------+
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# ...
```

If `nvidia-smi` works, your driver is correctly installed.

**Troubleshooting**: If `nvidia-smi` fails, see [Troubleshooting](#troubleshooting) section.

---

## Step 3: CUDA Toolkit Installation

vLLM requires CUDA Toolkit 12.1 or higher. We'll install CUDA 12.4 (compatible with PyTorch 2.9.0).

### 3.1 Download CUDA Repository Package

```bash
# Download CUDA keyring
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb

# Install keyring
sudo dpkg -i cuda-keyring_1.1-1_all.deb

# Update package list
sudo apt update
```

### 3.2 Install CUDA Toolkit

```bash
# Install CUDA Toolkit 12.4
sudo apt install -y cuda-toolkit-12-4

# This installs to /usr/local/cuda-12.4
```

**Alternative**: Install specific CUDA version:

```bash
# For CUDA 12.1 (minimum)
sudo apt install -y cuda-toolkit-12-1

# For CUDA 12.9 (latest as of vLLM development)
sudo apt install -y cuda-toolkit-12-9
```

**Time**: ~10-15 minutes

### 3.3 Set Up CUDA Environment Variables

```bash
# Add CUDA to PATH
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc

# Apply changes
source ~/.bashrc

# Create symlink to latest CUDA
sudo ln -sf /usr/local/cuda-12.4 /usr/local/cuda
```

### 3.4 Verify CUDA Installation

```bash
# Check CUDA version
nvcc --version

# Expected output:
# nvcc: NVIDIA (R) Cuda compiler driver
# Copyright (c) 2005-2024 NVIDIA Corporation
# ...
# Cuda compilation tools, release 12.4, V12.4.xxx

# Check CUDA samples (optional)
/usr/local/cuda/bin/cuda-install-samples-12.4.sh ~
cd ~/NVIDIA_CUDA-12.4_Samples/1_Utilities/deviceQuery
make
./deviceQuery

# Expected: Device information displayed
```

---

## Step 4: Python Environment Setup

vLLM requires Python 3.10, 3.11, 3.12, or 3.13. We'll use Python 3.12 (recommended).

### 4.1 Install Python 3.12

Ubuntu 24.04 comes with Python 3.12 by default:

```bash
# Check Python version
python3 --version

# Expected: Python 3.12.x
```

If you need a different version:

```bash
# Add deadsnakes PPA for other Python versions
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update

# Install Python 3.11 (example)
sudo apt install -y python3.11 python3.11-dev python3.11-venv

# Or Python 3.13
sudo apt install -y python3.13 python3.13-dev python3.13-venv
```

### 4.2 Install Python Development Tools

```bash
# Install Python development headers and tools
sudo apt install -y \
    python3-dev \
    python3-pip \
    python3-venv \
    python3-wheel \
    python3-setuptools
```

### 4.3 Upgrade pip

```bash
# Upgrade pip to latest version
python3 -m pip install --upgrade pip

# Install build tools
python3 -m pip install --upgrade setuptools wheel
```

### 4.4 Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python3 -m venv ~/vllm-env

# Activate virtual environment
source ~/vllm-env/bin/activate

# Your prompt should change to:
# (vllm-env) user@hostname:~$

# Upgrade pip in venv
pip install --upgrade pip setuptools wheel
```

**IMPORTANT**: Always activate this environment before using vLLM:
```bash
source ~/vllm-env/bin/activate
```

To deactivate:
```bash
deactivate
```

---

## Step 5: Build Dependencies

### 5.1 Install System Build Dependencies

```bash
# Install compilers and build tools
sudo apt install -y \
    gcc \
    g++ \
    make \
    cmake \
    ninja-build \
    ccache \
    pkg-config

# Install additional libraries
sudo apt install -y \
    libssl-dev \
    libffi-dev \
    libnuma-dev \
    libopenmpi-dev
```

### 5.2 Verify CMake Version

vLLM requires CMake 3.26+:

```bash
# Check CMake version
cmake --version

# Expected: cmake version 3.28.x or higher (Ubuntu 24.04 default)
```

If CMake is too old:

```bash
# Install latest CMake from Kitware APT repository
sudo apt remove --purge cmake -y
sudo apt update

# Add Kitware APT repository
wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null | gpg --dearmor - | sudo tee /etc/apt/trusted.gpg.d/kitware.gpg >/dev/null

sudo apt-add-repository "deb https://apt.kitware.com/ubuntu/ $(lsb_release -cs) main"
sudo apt update

# Install CMake
sudo apt install -y cmake

# Verify
cmake --version  # Should be 3.30+
```

### 5.3 Install Python Build Dependencies

```bash
# Activate venv if not already
source ~/vllm-env/bin/activate

# Install build dependencies
pip install --upgrade \
    cmake>=3.26 \
    ninja \
    packaging \
    setuptools>=77.0.3 \
    setuptools-scm>=8.0 \
    wheel \
    jinja2
```

**Time**: ~2-5 minutes

---

## Step 6: Clone vLLM Repository

### 6.1 Clone Repository

```bash
# Navigate to home or desired directory
cd ~

# Clone vLLM repository
git clone https://github.com/vllm-project/vllm.git

# Enter directory
cd vllm

# Check current version
git describe --tags --always
```

### 6.2 (Optional) Checkout Specific Version

```bash
# List available tags
git tag -l

# Checkout specific version (example: v0.6.0)
git checkout v0.6.0

# Or stay on main branch for latest development
git checkout main
```

### 6.3 Update Submodules

```bash
# Initialize and update submodules
git submodule update --init --recursive
```

**Time**: ~2-5 minutes (depends on network speed)

---

## Step 7: Build vLLM

### 7.1 Install PyTorch with CUDA Support

vLLM requires PyTorch 2.9.0 with CUDA support:

```bash
# Activate venv
source ~/vllm-env/bin/activate

# Install PyTorch 2.9.0 with CUDA 12.4 support
pip install torch==2.9.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Verify PyTorch installation
python3 -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}')"

# Expected output:
# PyTorch version: 2.9.0
# CUDA available: True
# CUDA version: 12.4
```

**If CUDA not available**: Check NVIDIA driver and CUDA installation.

**Time**: ~5-10 minutes

### 7.2 Set Build Environment Variables

```bash
# Export CUDA architecture for your GPU
# For RTX 30xx: 8.6
# For RTX 40xx: 8.9
# For A100: 8.0
# For H100: 9.0
# For multiple architectures (recommended):
export TORCH_CUDA_ARCH_LIST="7.0;7.5;8.0;8.6;8.9;9.0"

# Use ccache for faster rebuilds (optional)
export CMAKE_BUILD_TYPE=Release
export CCACHE_DIR=~/.ccache
export PATH="/usr/lib/ccache:$PATH"

# Enable ninja for faster builds
export CMAKE_GENERATOR=Ninja

# Specify CUDA path explicitly (if needed)
export CUDA_HOME=/usr/local/cuda
export CUDACXX=/usr/local/cuda/bin/nvcc
```

**Understanding CUDA Architecture**:
- Find your GPU's compute capability at: https://developer.nvidia.com/cuda-gpus
- Common values:
  - 7.0: V100
  - 7.5: T4, Quadro RTX
  - 8.0: A100
  - 8.6: RTX 30xx (3060, 3070, 3080, 3090)
  - 8.9: RTX 40xx (4070, 4080, 4090), L4, L40
  - 9.0: H100, H200

### 7.3 Build vLLM from Source

**Method A: Build and Install in One Step (Recommended)**

```bash
# Navigate to vLLM directory
cd ~/vllm

# Activate venv
source ~/vllm-env/bin/activate

# Build and install vLLM
pip install -e .

# The -e flag installs in "editable" mode (useful for development)
# For production, use: pip install .
```

**Method B: Build with Verbose Output (for debugging)**

```bash
# Build with verbose output to see compilation details
VERBOSE=1 pip install -v -e .
```

**Method C: Build with CMake Directly**

```bash
# Create build directory
mkdir -p build && cd build

# Configure with CMake
cmake -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DVLLM_PYTHON_EXECUTABLE=$(which python3) \
    -DCMAKE_INSTALL_PREFIX=.. \
    ..

# Build
cmake --build . --target install

# Then install Python package
cd ..
pip install -e .
```

**Build Time**: ~20-40 minutes (depends on CPU cores and architecture list)

During build, you should see:
```
Building wheels for collected packages: vllm
  Building editable for vllm (pyproject.toml) ...
  [Lots of compilation output]
  Successfully built vllm
Installing collected packages: vllm
Successfully installed vllm-0.x.x
```

### 7.4 Monitor Build Progress

If build seems stuck, open another terminal:

```bash
# Monitor GPU usage (if using GPU for compilation)
watch -n 1 nvidia-smi

# Monitor CPU usage
htop

# Check build logs
tail -f /tmp/pip-install-*/vllm/build.log
```

---

## Step 8: Install vLLM

If you used `pip install -e .` in step 7.3, vLLM is already installed. Otherwise:

### 8.1 Install Additional Dependencies

```bash
# Activate venv
source ~/vllm-env/bin/activate

# Install vLLM with all dependencies
cd ~/vllm
pip install -e .[all]

# Or install specific feature sets:
# pip install -e .[tensorrt]  # For TensorRT support
# pip install -e .[all]       # All optional dependencies
```

### 8.2 Install Common Model Dependencies

```bash
# Install transformers and common dependencies
pip install \
    transformers>=4.40.0 \
    tokenizers>=0.19.0 \
    huggingface-hub>=0.23.0 \
    numpy \
    pillow \
    requests

# Install FastAPI for serving (if using OpenAI-compatible server)
pip install \
    fastapi \
    uvicorn[standard] \
    pydantic \
    aiohttp
```

**Time**: ~5-10 minutes

---

## Step 9: Verification & Testing

### 9.1 Verify Installation

```bash
# Activate venv
source ~/vllm-env/bin/activate

# Check vLLM installation
python3 -c "import vllm; print(f'vLLM version: {vllm.__version__}')"

# Expected output:
# vLLM version: 0.x.x

# Check CUDA integration
python3 -c "import torch; import vllm; print('vLLM CUDA available:', torch.cuda.is_available())"

# Expected: vLLM CUDA available: True
```

### 9.2 Run Basic Test

```bash
# Test with a small model (if you have internet and disk space)
python3 -c "
from vllm import LLM

# This will download facebook/opt-125m model (~250MB)
llm = LLM(model='facebook/opt-125m')

prompts = ['Hello, my name is', 'The capital of France is']
outputs = llm.generate(prompts)

for output in outputs:
    print(f'Prompt: {output.prompt}')
    print(f'Output: {output.outputs[0].text}')
    print('---')
"
```

**Expected Output**: Model should load and generate text.

### 9.3 Run vLLM Server Test

```bash
# Start vLLM OpenAI-compatible server
vllm serve facebook/opt-125m --port 8000 &

# Wait for server to start (~10 seconds)
sleep 10

# Test with curl
curl http://localhost:8000/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "facebook/opt-125m",
        "prompt": "San Francisco is a",
        "max_tokens": 20,
        "temperature": 0
    }'

# Stop server
pkill -f "vllm serve"
```

**Expected**: JSON response with generated text.

### 9.4 Check GPU Utilization

```bash
# In one terminal, run vLLM
vllm serve facebook/opt-125m

# In another terminal, monitor GPU
watch -n 0.5 nvidia-smi

# You should see GPU memory used and GPU utilization percentage
```

### 9.5 Run Unit Tests (Optional)

```bash
cd ~/vllm

# Install test dependencies
pip install pytest pytest-asyncio

# Run basic tests
pytest tests/basic_correctness -v

# Run model tests
pytest tests/models -v -k "opt"
```

---

## Troubleshooting

### Problem 1: nvidia-smi Not Found

**Symptoms**:
```
Command 'nvidia-smi' not found
```

**Solutions**:
```bash
# 1. Check if driver is installed
dpkg -l | grep nvidia-driver

# 2. If not installed, install driver
sudo ubuntu-drivers install
sudo reboot

# 3. If driver is installed but nvidia-smi not found
sudo apt install --reinstall nvidia-utils-550

# 4. Check kernel module
lsmod | grep nvidia
# If empty, load module:
sudo modprobe nvidia
```

### Problem 2: CUDA Not Available in PyTorch

**Symptoms**:
```python
torch.cuda.is_available()  # Returns False
```

**Solutions**:
```bash
# 1. Verify CUDA toolkit installation
nvcc --version

# 2. Reinstall PyTorch with correct CUDA version
pip uninstall torch torchvision torchaudio
pip install torch==2.9.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 3. Check LD_LIBRARY_PATH
echo $LD_LIBRARY_PATH
# Should include /usr/local/cuda/lib64

# 4. Add to .bashrc if missing
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### Problem 3: Build Fails with "No CUDA toolset found"

**Symptoms**:
```
CMake Error: No CUDA toolset found
```

**Solutions**:
```bash
# 1. Ensure CUDA_HOME is set
export CUDA_HOME=/usr/local/cuda
export PATH=/usr/local/cuda/bin:$PATH

# 2. Verify nvcc is accessible
which nvcc
nvcc --version

# 3. Create symlink if needed
sudo ln -sf /usr/local/cuda-12.4 /usr/local/cuda

# 4. Retry build
pip install -e . --no-cache-dir
```

### Problem 4: Out of Memory During Build

**Symptoms**:
```
c++: fatal error: Killed signal terminated program cc1plus
```

**Solutions**:
```bash
# 1. Reduce parallel build jobs
export MAX_JOBS=4
pip install -e .

# 2. Build only for your GPU architecture
export TORCH_CUDA_ARCH_LIST="8.6"  # For RTX 30xx
pip install -e .

# 3. Add swap space
sudo fallocate -l 16G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 4. Close other applications
```

### Problem 5: ImportError: libcuda.so.1

**Symptoms**:
```
ImportError: libcuda.so.1: cannot open shared object file
```

**Solutions**:
```bash
# 1. Find libcuda.so.1
sudo find /usr -name "libcuda.so*"

# 2. Add to LD_LIBRARY_PATH (usually in /usr/lib/x86_64-linux-gnu)
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH

# 3. Update ldconfig
sudo ldconfig

# 4. Add to .bashrc
echo 'export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH' >> ~/.bashrc
```

### Problem 6: ModuleNotFoundError: No module named 'vllm'

**Symptoms**:
```
ModuleNotFoundError: No module named 'vllm'
```

**Solutions**:
```bash
# 1. Ensure virtual environment is activated
source ~/vllm-env/bin/activate

# 2. Check if vllm is installed
pip list | grep vllm

# 3. Reinstall if needed
cd ~/vllm
pip install -e .

# 4. Check Python path
python3 -c "import sys; print('\n'.join(sys.path))"
```

### Problem 7: GLIBC Version Errors

**Symptoms**:
```
version `GLIBC_2.34' not found
```

**Solutions**:
```bash
# 1. Check GLIBC version
ldd --version

# Ubuntu 24.04 has GLIBC 2.39, should be fine

# 2. If using pre-built wheels, build from source instead
pip uninstall vllm
cd ~/vllm
pip install -e .

# 3. Ensure you're on Ubuntu 24.04
lsb_release -a
```

### Problem 8: CUDA Architecture Mismatch

**Symptoms**:
```
RuntimeError: CUDA error: no kernel image is available for execution on the device
```

**Solutions**:
```bash
# 1. Find your GPU's compute capability
nvidia-smi --query-gpu=compute_cap --format=csv

# 2. Rebuild with correct architecture
export TORCH_CUDA_ARCH_LIST="8.6"  # Use your GPU's compute capability
pip uninstall vllm
cd ~/vllm
pip install -e . --no-cache-dir

# 3. For multiple GPUs with different architectures
export TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9"
pip install -e . --no-cache-dir
```

### Problem 9: Build Takes Forever

**Symptoms**: Build is extremely slow

**Solutions**:
```bash
# 1. Use ccache
sudo apt install ccache
export PATH="/usr/lib/ccache:$PATH"
export CCACHE_DIR=~/.ccache

# 2. Use ninja instead of make
export CMAKE_GENERATOR=Ninja
sudo apt install ninja-build

# 3. Limit CUDA architectures
export TORCH_CUDA_ARCH_LIST="8.6"  # Only your GPU

# 4. Increase parallel jobs (if you have RAM)
export MAX_JOBS=8

# 5. Clean and rebuild
cd ~/vllm
rm -rf build dist *.egg-info
pip install -e .
```

### Problem 10: Permission Denied Errors

**Symptoms**:
```
PermissionError: [Errno 13] Permission denied
```

**Solutions**:
```bash
# 1. Don't use sudo with pip in venv
source ~/vllm-env/bin/activate
pip install -e .  # NO sudo

# 2. Fix ownership of venv
sudo chown -R $USER:$USER ~/vllm-env

# 3. Fix .cache directory
sudo chown -R $USER:$USER ~/.cache

# 4. If building in /opt or /usr/local, use proper permissions
# Better: build in user directory (~/vllm)
```

---

## Performance Tuning

### Enable Persistent GPU Mode

```bash
# Enable persistence mode (reduces GPU initialization overhead)
sudo nvidia-smi -pm 1

# Set max performance mode
sudo nvidia-smi -i 0 -pl 350  # Set power limit (adjust for your GPU)

# Lock GPU clocks to max (for consistent performance)
sudo nvidia-smi -i 0 -lgc 2100  # Lock GPU clock to 2100 MHz (adjust for your GPU)
```

### Optimize for Large Models

```bash
# Increase file descriptor limit
echo "* soft nofile 65535" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65535" | sudo tee -a /etc/security/limits.conf

# Increase shared memory size (for tensor parallelism)
sudo mount -o remount,size=16G /dev/shm

# Make permanent
echo "tmpfs /dev/shm tmpfs defaults,size=16G 0 0" | sudo tee -a /etc/fstab
```

### Configure System for High Performance

```bash
# Disable CPU frequency scaling (use performance governor)
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Make permanent
sudo apt install cpufrequtils
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo systemctl disable ondemand
```

### Environment Variables for Production

Create `~/vllm-env.sh`:

```bash
#!/bin/bash

# Activate vLLM environment
source ~/vllm-env/bin/activate

# CUDA settings
export CUDA_HOME=/usr/local/cuda
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# vLLM optimizations
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_USE_MODELSCOPE=False
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1

# Networking (for distributed inference)
export NCCL_DEBUG=INFO
export NCCL_IB_DISABLE=1  # Disable InfiniBand if not available
export NCCL_SOCKET_IFNAME=lo

# PyTorch settings
export OMP_NUM_THREADS=8
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

echo "vLLM environment loaded"
```

Make executable and use:
```bash
chmod +x ~/vllm-env.sh
source ~/vllm-env.sh
```

---

## Uninstallation

### Uninstall vLLM

```bash
# Activate venv
source ~/vllm-env/bin/activate

# Uninstall vLLM
pip uninstall vllm -y

# Remove build artifacts
cd ~/vllm
rm -rf build dist *.egg-info
```

### Remove Virtual Environment

```bash
# Deactivate if active
deactivate

# Remove venv
rm -rf ~/vllm-env
```

### Remove CUDA Toolkit (Optional)

```bash
# Remove CUDA packages
sudo apt remove --purge cuda-toolkit-* -y
sudo apt autoremove -y

# Remove CUDA directories
sudo rm -rf /usr/local/cuda*
```

### Remove NVIDIA Drivers (Optional)

**WARNING**: Only do this if you're sure you want to remove all NVIDIA software.

```bash
# Remove NVIDIA packages
sudo apt remove --purge nvidia-* libnvidia-* -y
sudo apt autoremove -y

# Remove NVIDIA directories
sudo rm -rf /usr/lib/nvidia
sudo rm -rf /etc/nvidia

# Update initramfs
sudo update-initramfs -u

# Reboot
sudo reboot
```

---

## Quick Reference: Complete Build Script

Save as `build_vllm.sh`:

```bash
#!/bin/bash
set -e

echo "=== vLLM Build Script for Ubuntu 24.04 + NVIDIA ==="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Update system
echo -e "${GREEN}[1/9] Updating system...${NC}"
sudo apt update && sudo apt upgrade -y

# 2. Install NVIDIA driver
echo -e "${GREEN}[2/9] Installing NVIDIA driver...${NC}"
sudo ubuntu-drivers install
echo -e "${YELLOW}REBOOT REQUIRED. Run this script again after reboot.${NC}"
read -p "Press Enter to reboot or Ctrl+C to cancel..."
sudo reboot

# Run after reboot:

# 3. Install CUDA
echo -e "${GREEN}[3/9] Installing CUDA Toolkit...${NC}"
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y cuda-toolkit-12-4

# 4. Set up environment
echo -e "${GREEN}[4/9] Setting up environment...${NC}"
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# 5. Install build dependencies
echo -e "${GREEN}[5/9] Installing build dependencies...${NC}"
sudo apt install -y \
    build-essential \
    cmake \
    ninja-build \
    ccache \
    python3-dev \
    python3-pip \
    python3-venv

# 6. Create venv
echo -e "${GREEN}[6/9] Creating virtual environment...${NC}"
python3 -m venv ~/vllm-env
source ~/vllm-env/bin/activate

# 7. Install PyTorch
echo -e "${GREEN}[7/9] Installing PyTorch...${NC}"
pip install torch==2.9.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 8. Clone and build vLLM
echo -e "${GREEN}[8/9] Cloning and building vLLM...${NC}"
cd ~
git clone https://github.com/vllm-project/vllm.git
cd vllm
git submodule update --init --recursive

export TORCH_CUDA_ARCH_LIST="7.0;7.5;8.0;8.6;8.9;9.0"
export CMAKE_BUILD_TYPE=Release

pip install -e .

# 9. Verify
echo -e "${GREEN}[9/9] Verifying installation...${NC}"
python3 -c "import vllm; print(f'vLLM version: {vllm.__version__}')"
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

echo -e "${GREEN}=== Build Complete! ===${NC}"
echo "To activate vLLM environment: source ~/vllm-env/bin/activate"
```

---

## Additional Resources

### Official Documentation

- vLLM Documentation: https://docs.vllm.ai/
- vLLM GitHub: https://github.com/vllm-project/vllm
- NVIDIA CUDA Documentation: https://docs.nvidia.com/cuda/

### Community

- vLLM Slack: https://slack.vllm.ai/
- GitHub Issues: https://github.com/vllm-project/vllm/issues
- GitHub Discussions: https://github.com/vllm-project/vllm/discussions

### Model Resources

- Hugging Face Models: https://huggingface.co/models
- vLLM Supported Models: https://docs.vllm.ai/en/latest/models/supported_models.html

### Benchmark & Performance

- vLLM Performance Benchmarks: https://github.com/vllm-project/vllm/tree/main/benchmarks
- Model Serving Guide: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-01-XX | 1.0 | Initial release for Ubuntu 24.04 |

---

## License

This guide is provided as-is for the vLLM community. vLLM itself is licensed under Apache 2.0.

---

## Credits

Created for the vLLM community. Based on official vLLM documentation and Ubuntu 24.04 best practices.

For issues or improvements to this guide, please submit an issue or PR to the vLLM repository.
