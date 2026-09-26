# Base image carries CUDA and a matching torch, so only the serving layer is
# installed here. The tag is pinned: `latest` would make the CUDA and driver
# combination vary between rentals.
FROM vllm/vllm-openai:v0.28.0

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY start_vllm.sh healthcheck.sh collect_metrics.sh ./
COPY stress_test.py run_qualification.sh ./
COPY configs/ ./configs/
RUN chmod +x *.sh

# Model weights are a mounted volume, never baked in: a 30-60 GB layer would be
# re-pulled on every rental, and the checkpoint is pinned by revision anyway.
VOLUME /models
ENV HF_HOME=/models/hf

EXPOSE 8000
ENTRYPOINT ["/srv/start_vllm.sh"]
