FROM ubuntu:22.04

# 设置工作目录
WORKDIR /app

# 安装必要的工具和 Python 3.11
RUN apt-get update && apt-get install -y \
    gnupg \
    lsb-release \
    && echo "deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ $(lsb_release -cs) main restricted universe multiverse" > /etc/apt/sources.list.d/tuna.list \
    && echo "deb-src https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ $(lsb_release -cs) main restricted universe multiverse" >> /etc/apt/sources.list.d/tuna.list \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    wget \
    curl \
    git \
    libgl1 \
    libglvnd0 \
    libglib2.0-0 \
    libgtk2.0-0 \
    vim \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv 
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# 设置镜像源
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 创建虚拟环境
RUN uv venv /opt/venv --python=python3.11

# 激活虚拟环境
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制 requirements.txt 到工作目录
COPY requirements.txt /app/

# 使用 uv 安装依赖
RUN uv pip install --no-deps -r requirements.txt 

# 迁移数据至docker工作目录
COPY . /app/

# 设置暴露端口
ARG SVR_PORT=20009
ENV PORT=${SVR_PORT}
EXPOSE ${SVR_PORT}

# 启动服务
ENV PYTHONPATH=/app
CMD ["uv", "run", "python", "-m", "app"]