import streamlit as st
import stripe
from datetime import datetime, timedelta
from typing import Optional, Dict
import os

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
            subscription = stripe.Subscription.retrieve(subscription_id)
            subscription.delete()
            return True
        
        except Exception as e:
            st.error(f"Cancellation error: {str(e)}")
            return False
    
    @staticmethod
    def handle_webhook(payload: dict, sig_header: str, webhook_secret: str):
        """
        Handle Stripe webhook events to update user subscriptions
        
        Usage in production (Flask/FastAPI endpoint):
        
        @app.post("/webhook/stripe")
        def stripe_webhook():
            payload = request.data
            sig_header = request.headers.get('Stripe-Signature')
            
            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, webhook_secret
                )
                
                if event['type'] == 'checkout.session.completed':
                    session = event['data']['object']
                    user_id = session.get('client_reference_id')
                    customer_id = session.get('customer')
                    subscription_id = session.get('subscription')
                    
                    # Update database
                    db = Database()
                    conn = db.get_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute('''
                        UPDATE users 
                        SET is_premium = 1, 
                            premium_expires_at = datetime('now', '+30 days')
                        WHERE user_id = ?
                    ''', (user_id,))
                    
                    cursor.execute('''
                        INSERT INTO subscriptions 
                        (user_id, stripe_customer_id, stripe_subscription_id, status)
                        VALUES (?, ?, ?, 'active')
                    ''', (user_id, customer_id, subscription_id))
                    
                    conn.commit()
                    conn.close()
                    
                elif event['type'] == 'customer.subscription.deleted':
                    subscription = event['data']['object']
                    subscription_id = subscription['id']
                    
                    # Update database
                    db = Database()
                    conn = db.get_connection()
                    cursor = conn.cursor()
                    
                    cursor.execute('''
                        UPDATE subscriptions 
                        SET status = 'cancelled'
                        WHERE stripe_subscription_id = ?
                    ''', (subscription_id,))
                    
                    cursor.execute('''
                        SELECT user_id FROM subscriptions 
                        WHERE stripe_subscription_id = ?
                    ''', (subscription_id,))
                    
                    user = cursor.fetchone()
                    if user:
                        cursor.execute('''
                            UPDATE users 
                            SET is_premium = 0
                            WHERE user_id = ?
                        ''', (user['user_id'],))
                    
                    conn.commit()
                    conn.close()
                
                return {'success': True}
                
            except Exception as e:
                return {'error': str(e)}, 400
        """
        pass

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
