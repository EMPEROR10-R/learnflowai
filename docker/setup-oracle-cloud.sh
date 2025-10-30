#!/bin/bash

echo "🚀 LearnFlow AI - Oracle Cloud Free VM Setup"
echo "=============================================="

echo "📦 Step 1: Updating system packages..."
sudo apt update && sudo apt upgrade -y

echo "🐍 Step 2: Installing Python and dependencies..."
sudo apt install -y python3 python3-pip git nginx certbot python3-certbot-nginx

echo "🤖 Step 3: Installing Ollama (Self-Hosted AI)..."
curl -fsSL https://ollama.ai/install.sh | sh

echo "📥 Step 4: Downloading Llama 3 model (this may take a few minutes)..."
ollama pull llama3

echo "🔧 Step 5: Cloning LearnFlow AI..."
cd /home/ubuntu
git clone https://github.com/yourusername/learnflow-ai.git
cd learnflow-ai

echo "📚 Step 6: Installing Python dependencies..."
pip3 install -r requirements.txt

echo "⚙️ Step 7: Setting up systemd service..."
sudo tee /etc/systemd/system/learnflow.service > /dev/null <<EOF
[Unit]
Description=LearnFlow AI
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/learnflow-ai
ExecStart=/usr/local/bin/streamlit run app.py --server.port 8501
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "🔧 Step 8: Setting up Ollama systemd service..."
sudo tee /etc/systemd/system/ollama.service > /dev/null <<EOF
[Unit]
Description=Ollama Service
After=network.target

[Service]
Type=simple
User=ubuntu
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "🌐 Step 9: Configuring Nginx..."
sudo tee /etc/nginx/sites-available/learnflow > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/learnflow /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t

echo "🚀 Step 10: Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl enable learnflow
sudo systemctl start learnflow
sudo systemctl restart nginx

echo "🔥 Step 11: Opening firewall ports..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

echo ""
echo "✅ Installation Complete!"
echo "========================="
echo ""
echo "Your LearnFlow AI is now running at:"
echo "http://$(curl -s ifconfig.me)"
echo ""
echo "Next steps:"
echo "1. Point your domain to this IP address"
echo "2. Run: sudo certbot --nginx -d yourdomain.com"
echo "3. Add your Groq API key in the app sidebar"
echo ""
echo "Service Management:"
echo "- Check status: sudo systemctl status learnflow"
echo "- View logs: sudo journalctl -u learnflow -f"
echo "- Restart: sudo systemctl restart learnflow"
echo ""
echo "🎉 Happy Learning!"
