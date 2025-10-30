# Oracle Cloud Free VM Deployment

This directory contains scripts and configuration for deploying LearnFlow AI on Oracle Cloud's Always Free tier.

## Oracle Cloud Free Tier Specs

- **CPU**: 4-core ARM Ampere A1
- **RAM**: 24GB
- **Storage**: 200GB
- **Bandwidth**: 10TB/month
- **Cost**: $0 forever

## Quick Setup

### 1. Create Oracle Cloud Account

1. Go to https://oracle.com/cloud/free
2. Sign up for free account (no credit card for Always Free resources)
3. Verify your account

### 2. Launch VM Instance

1. Go to Compute → Instances → Create Instance
2. Select:
   - **Image**: Ubuntu 22.04 (ARM)
   - **Shape**: VM.Standard.A1.Flex
   - **CPUs**: 4
   - **Memory**: 24GB
3. Download SSH key
4. Click "Create"

### 3. SSH Into Your VM

```bash
ssh -i your-ssh-key.pem ubuntu@your-vm-ip
```

### 4. Run Setup Script

```bash
# Download and run the setup script
curl -fsSL https://raw.githubusercontent.com/yourusername/learnflow-ai/main/docker/setup-oracle-cloud.sh | bash
```

That's it! The script will:
- Install all dependencies
- Set up Ollama with Llama 3
- Configure Nginx reverse proxy
- Start LearnFlow AI automatically
- Set up systemd services for auto-restart

## Manual Setup

If you prefer manual setup, follow these steps:

### Install Ollama

```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3
ollama serve
```

### Install LearnFlow AI

```bash
git clone https://github.com/yourusername/learnflow-ai.git
cd learnflow-ai
pip3 install -r requirements.txt
streamlit run app.py --server.port 8501
```

### Configure Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### Enable HTTPS with Let's Encrypt

```bash
sudo certbot --nginx -d your-domain.com
```

## Docker Deployment (Alternative)

```bash
cd docker
docker-compose up -d
```

## Monitoring

### Check Service Status

```bash
sudo systemctl status learnflow
sudo systemctl status ollama
```

### View Logs

```bash
# LearnFlow logs
sudo journalctl -u learnflow -f

# Ollama logs
sudo journalctl -u ollama -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
```

## Performance Tuning

### Optimize Ollama

```bash
# Use GPU acceleration (if available)
OLLAMA_NUM_GPU=1 ollama serve

# Adjust concurrent requests
OLLAMA_MAX_LOADED_MODELS=2 ollama serve
```

### Optimize Streamlit

Edit `config.toml`:
```toml
[server]
maxUploadSize = 10
enableCORS = false
enableXsrfProtection = true
```

## Scaling to 100k+ Users

1. **Load Balancing**: Use Oracle Cloud Load Balancer (free tier available)
2. **Multiple Instances**: Deploy on multiple free VMs
3. **CDN**: Use Cloudflare (free) for static assets
4. **Database**: Upgrade to PostgreSQL if needed
5. **Caching**: Add Redis for session management

## Cost Breakdown

- **VM**: $0 (Always Free)
- **Bandwidth**: $0 (10TB included)
- **Load Balancer**: $0 (Free tier: 10Mbps)
- **Domain**: ~$10/year (optional)
- **SSL Certificate**: $0 (Let's Encrypt)

**Total Monthly Cost**: $0.83/month (domain only)

## Troubleshooting

### Port 80/443 Not Accessible

```bash
# Open firewall
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

### Ollama Not Starting

```bash
# Check logs
sudo journalctl -u ollama -n 50

# Restart service
sudo systemctl restart ollama
```

### Out of Memory

```bash
# Add swap space
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

## Security Best Practices

1. **Firewall**: Only open ports 80, 443, and SSH
2. **SSH**: Disable password auth, use keys only
3. **Updates**: Enable automatic security updates
4. **Fail2ban**: Install to prevent brute force attacks

```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

## Support

For issues specific to Oracle Cloud deployment, see:
- [Oracle Cloud Docs](https://docs.oracle.com/en-us/iaas/Content/home.htm)
- [LearnFlow AI Issues](https://github.com/yourusername/learnflow-ai/issues)
