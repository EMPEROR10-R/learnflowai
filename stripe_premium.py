import streamlit as st
import stripe
from datetime import datetime, timedelta
from typing import Optional, Dict

class StripePremium:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        if api_key:
            stripe.api_key = api_key
    
    def create_checkout_session(self, user_id: str, success_url: str, cancel_url: str) -> Optional[Dict]:
        if not self.api_key:
            return None
        
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': 'LearnFlow AI Premium',
                            'description': 'Unlimited AI queries, PDF uploads, advanced analytics, and more!',
                        },
                        'unit_amount': 499,
                        'recurring': {
                            'interval': 'month',
                        },
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=user_id,
                metadata={
                    'user_id': user_id,
                    'plan': 'premium'
                }
            )
            
            return {
                'session_id': session.id,
                'url': session.url
            }
        
        except Exception as e:
            st.error(f"Stripe error: {str(e)}")
            return None
    
    def create_customer_portal_session(self, customer_id: str, return_url: str) -> Optional[str]:
        if not self.api_key:
            return None
        
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session.url
        
        except Exception as e:
            st.error(f"Stripe portal error: {str(e)}")
            return None
    
    def verify_subscription(self, subscription_id: str) -> bool:
        if not self.api_key:
            return False
        
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return subscription.status in ['active', 'trialing']
        
        except Exception as e:
            return False
    
    def cancel_subscription(self, subscription_id: str) -> bool:
        if not self.api_key:
            return False
        
        try:
            stripe.Subscription.delete(subscription_id)
            return True
        
        except Exception as e:
            st.error(f"Cancellation error: {str(e)}")
            return False

def show_premium_upgrade_banner():
    st.markdown("""
        <style>
        .premium-banner {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 10px;
            color: white;
            margin: 20px 0;
            text-align: center;
        }
        .premium-feature {
            display: inline-block;
            margin: 5px 10px;
            padding: 5px 10px;
            background: rgba(255,255,255,0.2);
            border-radius: 5px;
        }
        </style>
        
        <div class="premium-banner">
            <h2>🚀 Upgrade to Premium for $4.99/month</h2>
            <p>Unlock unlimited learning potential!</p>
            <div>
                <span class="premium-feature">♾️ Unlimited AI Queries</span>
                <span class="premium-feature">📚 Unlimited PDF Uploads</span>
                <span class="premium-feature">📊 Advanced Analytics</span>
                <span class="premium-feature">👨‍👩‍👧 Parent Dashboard</span>
                <span class="premium-feature">⚡ Priority Responses</span>
                <span class="premium-feature">🚫 Ad-Free</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

def show_premium_benefits():
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🆓 Free Tier")
        st.markdown("""
        - ✅ 10 AI queries per day
        - ✅ 1 PDF upload per day
        - ✅ Basic progress tracking
        - ✅ Multi-subject learning
        - ✅ Voice input
        - ✅ Multilingual support
        """)
    
    with col2:
        st.markdown("### 💎 Premium ($4.99/mo)")
        st.markdown("""
        - ✅ **Unlimited** AI queries
        - ✅ **Unlimited** PDF uploads
        - ✅ Advanced analytics & insights
        - ✅ Parent/Teacher dashboard
        - ✅ Offline lesson downloads
        - ✅ Priority support
        - ✅ Ad-free experience
        - ✅ Custom study plans
        """)
