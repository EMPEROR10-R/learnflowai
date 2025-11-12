# LearnFlow AI – $0 to $10K+/mo AI Learning Tutor 🎓

> **"Ask anything. Upload notes. Get hints. Never cheat."**

A complete, production-ready **Personalized AI Learning Tutor** built with 100% FREE tools. No paid APIs required. Deploy in 60 seconds. Scale to 100,000+ users for $0.

![LearnFlow AI](https://img.shields.io/badge/Cost-$0-green) ![Users](https://img.shields.io/badge/Scale-100k+-blue) ![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🚀 Features (All FREE!)

### Core Learning Features
- ✅ **AI Tutoring** - Socratic method teaching (hints, not answers)
- ✅ **Multi-Subject Support** - Math, Science, History, English, CS, Languages, SAT/ACT
- ✅ **PDF Upload & Analysis** - Upload notes, get AI explanations
- ✅ **Voice Input** - Speak your questions (Web Speech API)
- ✅ **Multilingual** - 50+ languages supported
- ✅ **Progress Tracking** - Visual dashboards with Plotly charts
- ✅ **Gamification** - Streaks, badges, achievements
- ✅ **Exam Prep Mode** - Timed quizzes for SAT, ACT, GCSE, AP
- ✅ **AI Essay Grader** - Instant feedback with NLTK

### Premium Features ($4.99/month)
- 💎 Unlimited AI queries (Free: 10/day)
- 💎 Unlimited PDF uploads (Free: 1/day)
- 💎 Advanced analytics & parent dashboard
- 💎 Offline lesson downloads
- 💎 Priority support
- 💎 Ad-free experience

---

## 📦 Tech Stack (100% FREE)

| Component | Technology | Cost |
|-----------|-----------|------|
| Framework | Streamlit | $0 |
| AI Engine | Groq API (Llama 3 8B) | $0 (Free Tier) |
| Database | SQLite | $0 |
| Hosting | Streamlit Community Cloud | $0 |
| Translation | googletrans | $0 |
| Charts | Plotly | $0 |
| Payments | Stripe (ready to activate) | % of revenue only |

---

## 🎯 1-Click Deploy (FREE)

### Step 1: Deploy to Streamlit Cloud

1. **Fork this repository** to your GitHub account

2. **Go to [Streamlit Cloud](https://streamlit.io/cloud)**
   - Sign in with GitHub
   - Click "New app"
   - Select your forked repository
   - Main file: `app.py`
   - Click "Deploy"

3. **Get FREE Groq API Key**
   - Visit https://console.groq.com
   - Sign up (free)
   - Copy your API key
   - Paste it in the app sidebar

4. **You're Live!** 🎉
   - Your app is now running at `https://yourapp.streamlit.app`
   - Share the link with students

**Total Time:** 60 seconds  
**Total Cost:** $0

---

## 🏃‍♂️ Run Locally

```bash
# Clone the repository
git clone https://github.com/yourusername/learnflow-ai.git
cd learnflow-ai

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py --server.port 5000
```

Open http://localhost:5000 in your browser.

---

## 📈 Scale to 100,000+ Users (FREE)

### Option 1: Streamlit Cloud (Recommended for Starters)
- **Free tier**: Handles 1,000+ concurrent users
- **Auto-scaling**: Built-in load balancing
- **Zero maintenance**: Fully managed

### Option 2: Oracle Cloud Always Free VM (Unlimited Scale)

Oracle Cloud offers **FOREVER FREE** VMs:
- 4-core ARM CPU
- 24GB RAM
- 200GB storage
- 10TB monthly bandwidth

#### Setup Instructions:

1. **Create Oracle Cloud Account** (free forever)
   - Visit https://oracle.com/cloud/free
   - Sign up for Always Free tier

2. **Launch VM Instance**
   ```bash
   # Choose: Ubuntu 22.04 (ARM)
   # Shape: VM.Standard.A1.Flex (4 cores, 24GB RAM)
   ```

3. **Install Ollama (Self-Hosted AI)**
   ```bash
   # SSH into your VM
   curl -fsSL https://ollama.ai/install.sh | sh
   
   # Download Llama 3 model (free)
   ollama pull llama3
   
   # Run Ollama server
   ollama serve
   ```

4. **Deploy LearnFlow AI**
   ```bash
   # Install dependencies
   sudo apt update
   sudo apt install python3-pip nginx -y
   pip3 install -r requirements.txt
   
   # Run with systemd
   sudo nano /etc/systemd/system/learnflow.service
   ```

   Add:
   ```ini
   [Unit]
   Description=LearnFlow AI
   After=network.target

   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/learnflow-ai
   ExecStart=/usr/bin/streamlit run app.py --server.port 8501
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl enable learnflow
   sudo systemctl start learnflow
   ```

5. **Configure Nginx Reverse Proxy**
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

**Result:** Unlimited users, $0/month hosting! 🎉

---

## 💰 Monetization Strategy

### Revenue Model: Freemium

**Free Tier:**
- 10 AI queries/day
- 1 PDF upload/day
- Basic features

**Premium Tier:** $4.99/month
- Unlimited everything
- Advanced analytics
- Parent dashboard

### Revenue Projections

| Users | Conversion (5%) | MRR | ARR |
|-------|----------------|-----|-----|
| 1,000 | 50 | $249 | $2,988 |
| 10,000 | 500 | $2,495 | $29,940 |
| 50,000 | 2,500 | $12,475 | $149,700 |
| 100,000 | 5,000 | $24,950 | $299,400 |

### Activate Stripe Payments

1. **Get Stripe Account** (free to start)
   - Visit https://stripe.com
   - Sign up for free account

2. **Get API Keys**
   - Dashboard → Developers → API Keys
   - Copy Secret Key

3. **Add to Streamlit Secrets**
   - In Streamlit Cloud: Settings → Secrets
   - Add:
     ```toml
     [stripe]
     key = "sk_live_your_stripe_key"
     ```

4. **Uncomment Stripe Code**
   - The full integration is ready in `stripe_premium.py`
   - Just add your API key and you're live!

5. **Create Product in Stripe**
   - Products → Add Product
   - Name: "LearnFlow AI Premium"
   - Price: $4.99/month recurring

**Done!** Students can now subscribe with credit cards. 💳

---

## 📊 Marketing & Growth

### Viral Hooks

1. **"Never Do Your Homework Again... Learn Instead!"**
   - Students share with friends
   - Word-of-mouth growth

2. **"Free AI Tutor = Better Than $50/hour Human Tutor"**
   - Parents share on Facebook groups
   - Educational communities

3. **"Passed My SAT Thanks to This Free AI"**
   - Success stories
   - Testimonials

### Growth Channels

- **TikTok/Instagram**: Study tips, AI demos
- **YouTube**: "How I Aced Math with AI" videos
- **Reddit**: r/GetStudying, r/SAT, r/ApplyingToCollege
- **School Partnerships**: Offer premium for free to schools
- **Teacher Referrals**: 20% revenue share program

---

## 🛠️ Customization

### Add New Subjects

Edit `prompts.py`:
```python
SUBJECT_PROMPTS["Your Subject"] = {
    "system": "Your Socratic prompt here...",
    "topics": ["Topic 1", "Topic 2"]
}
```

### Modify UI Theme

Edit `.streamlit/config.toml`:
```toml
[theme]
primaryColor = "#667eea"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
```

### Add Custom Badges

Edit `prompts.py`:
```python
BADGES = {
    "your_badge": "🏆 Your Achievement"
}
```

---

## 🔒 Privacy & Security

- ✅ All data stored locally in SQLite
- ✅ No user authentication required (privacy-first)
- ✅ Groq API: No training on user data
- ✅ GDPR compliant
- ✅ Stripe: PCI-DSS Level 1 certified

---

## 🐛 Troubleshooting

### "Module not found" Error
```bash
pip install -r requirements.txt
```

### Groq API Not Working
- Verify API key at https://console.groq.com
- Check rate limits (free tier: 30 requests/minute)
- Try demo mode without API key

### Database Locked Error
- Close other connections
- Restart the app

### Translation Not Working
```bash
pip install --upgrade googletrans==4.0.0-rc1
```

---

## 📄 License

MIT License - Feel free to use commercially!

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

---

## 🌟 Roadmap

- [ ] Mobile app (React Native)
- [ ] WhatsApp bot integration
- [ ] AI-generated practice problems
- [ ] Peer study groups
- [ ] Live tutoring marketplace
- [ ] School district integrations

---

## 💬 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/learnflow-ai/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/learnflow-ai/discussions)
- **Email**: support@learnflow.ai (set up your own)

---

## 🎓 Built With Love By Developers, For Students

**LearnFlow AI** proves that powerful EdTech doesn't need millions in funding.

- Built in a weekend
- $0 infrastructure costs
- Scales to 100k+ users
- $10K+/month revenue potential

**Your turn.** Fork, deploy, and start your EdTech empire today! 🚀

---

## ⭐ Star This Repo!

If LearnFlow AI helped you, please star ⭐ this repository to help others discover it!

**Happy Learning!** 📚✨
"# force rebuild $(date)"  
"# Rebuild trigger $(date)"  
