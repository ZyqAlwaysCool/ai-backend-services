FROM ubuntu:22.04

# 设置工作目录
WORKDIR /app

# 安装必要的工具
RUN apt-get update && apt-get install -y \
   gnupg \
   lsb-release \
   && echo "deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ $(lsb_release -cs) main restricted universe multiverse" > /etc/apt/sources.list.d/tuna.list \
   && echo "deb-src https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ $(lsb_release -cs) main restricted universe multiverse" >> /etc/apt/sources.list.d/tuna.list \
   && apt-get update && apt-get install -y \
   wget \
   curl \
   git \
   python3-pip \
   libgl1 \
   libglvnd0 \
   libglib2.0-0 \
   libgtk2.0-0 \
   vim \
   pandoc \
   && rm -rf /var/lib/apt/lists/*

# 下载并安装 Miniconda3
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm -f /tmp/miniconda.sh

# 添加 conda 到 PATH
ENV PATH=/opt/conda/bin:$PATH

# 配置 Conda 渠道并接受服务条款
RUN conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main && \
    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free && \
    conda config --set show_channel_urls yes && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# # 切换备用渠道源
# RUN conda config --add channels https://mirrors.ustc.edu.cn/anaconda/pkgs/main/ \
#     && conda config --add channels https://mirrors.ustc.edu.cn/anaconda/pkgs/free/ \
#     && conda config --set show_channel_urls yes \
#     && conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main \
#     && conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# 创建 conda 环境
RUN conda create -n myenv-311 python=3.11 -y

# 激活 conda 环境
ENV CONDA_DEFAULT_ENV=myenv-311
ENV CONDA_PREFIX=/opt/conda/envs/myenv-311
ENV PATH=/opt/conda/envs/myenv-311/bin:$PATH

# 配置 pip 使用阿里云镜像源
RUN conda run -n myenv-311 pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 复制 requirements.txt 到工作目录
COPY requirements.txt /app/

# 安装 requirements.txt 中的依赖
RUN conda run -n myenv-311 pip install -r requirements.txt

# 迁移数据至docker工作目录
COPY . /app/

# 设置暴露端口
ARG SVR_PORT=20009
ENV PORT=${SVR_PORT}
EXPOSE ${SVR_PORT}

# 启动服务
ENV PYTHONPATH=/app
CMD python -m app
