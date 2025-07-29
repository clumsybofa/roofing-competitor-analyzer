import streamlit as st
import requests
import json
import time
from typing import List, Dict, Optional, Tuple
import re
from dataclasses import dataclass
from geopy.distance import geodesic
import pandas as pd
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go

# Set page config
st.set_page_config(
    page_title="Roofing Competitor Analyzer",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Your API key - set this once for all users
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]  # Replace with your actual key

@dataclass
class Competitor:
    name: str
    address: str
    phone: str
    rating: float
    review_count: int
    website: str
    distance_miles: float
    pricing_info: List[str]
    services: List[str]
    positive_keywords: List[str]
    negative_keywords: List[str]
    review_themes: Dict[str, int]

class RoofingCompetitorAnalyzer:
    def __init__(self, google_api_key: str):
        self.api_key = google_api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place"
        
        # Keywords that indicate opportunities or pain points
        self.opportunity_keywords = {
            'speed': ['fast', 'quick', 'prompt', 'timely', 'on time', 'efficient'],
            'quality': ['quality', 'excellent', 'professional', 'skilled', 'expert', 'craftsmanship'],
            'price': ['affordable', 'reasonable', 'cheap', 'expensive', 'overpriced', 'fair price'],
            'communication': ['responsive', 'communicative', 'explained', 'kept informed', 'poor communication'],
            'cleanup': ['clean', 'cleanup', 'messy', 'left debris', 'neat', 'tidy'],
            'warranty': ['warranty', 'guarantee', 'stands behind work', 'honor warranty'],
            'insurance': ['insurance', 'claim', 'insurance work', 'help with insurance'],
            'emergency': ['emergency', 'urgent', 'storm damage', 'leak', 'immediate'],
            'materials': ['materials', 'shingles', 'metal', 'tile', 'membrane', 'quality materials'],
            'experience': ['experienced', 'years in business', 'knowledgeable', 'inexperienced'],
            'scheduling': ['flexible', 'scheduling', 'appointment', 'showed up', 'no show', 'late'],
            'estimate': ['free estimate', 'accurate estimate', 'detailed quote', 'overestimate']
        }
        
        self.negative_indicators = [
            'disappointed', 'unprofessional', 'rude', 'late', 'no show', 'poor',
            'terrible', 'awful', 'bad', 'worst', 'avoid', 'scam', 'overcharged',
            'shoddy', 'cheap work', 'leaked', 'failed', 'damaged', 'nightmare'
        ]
        
        self.positive_indicators = [
            'excellent', 'amazing', 'professional', 'recommend', 'great', 'fantastic',
            'wonderful', 'outstanding', 'perfect', 'impressed', 'satisfied', 'happy',
            'reliable', 'trustworthy', 'honest', 'fair', 'quality work'
        ]
    
    def geocode_address(self, address: str) -> tuple:
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json"
        params = {'address': address, 'key': self.api_key}
        response = requests.get(geocode_url, params=params)
        data = response.json()
        
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            raise Exception(f"Geocoding failed: {data['status']}")
    
    def search_nearby_roofing_companies(self, lat: float, lng: float, radius_miles: int = 5) -> List[Dict]:
        radius_meters = radius_miles * 1609.34
        search_url = f"{self.base_url}/nearbysearch/json"
        params = {
            'location': f"{lat},{lng}",
            'radius': int(radius_meters),
            'keyword': 'roofing contractor',
            'type': 'general_contractor',
            'key': self.api_key
        }
        
        all_results = []
        response = requests.get(search_url, params=params)
        data = response.json()
        
        if data['status'] == 'OK':
            all_results.extend(data['results'])
            
            while 'next_page_token' in data:
                time.sleep(2)
                params['pagetoken'] = data['next_page_token']
                response = requests.get(search_url, params=params)
                data = response.json()
                if data['status'] == 'OK':
                    all_results.extend(data['results'])
                else:
                    break
        
        return all_results
    
    def get_place_details(self, place_id: str) -> Dict:
        details_url = f"{self.base_url}/details/json"
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_address,formatted_phone_number,rating,user_ratings_total,website,reviews',
            'key': self.api_key
        }
        
        response = requests.get(details_url, params=params)
        data = response.json()
        
        if data['status'] == 'OK':
            return data['result']
        return {}
    
    def extract_pricing_from_reviews(self, reviews: List[Dict]) -> List[str]:
        pricing_info = []
        price_patterns = [
            r'\$[\d,]+', r'[\d,]+\s*dollars?', r'cost.*\$[\d,]+',
            r'price.*\$[\d,]+', r'quote.*\$[\d,]+', r'estimate.*\$[\d,]+',
            r'\$[\d,]+.*square\s*foot', r'[\d.]+\s*per\s*square\s*foot'
        ]
        
        for review in reviews:
            text = review.get('text', '').lower()
            for pattern in price_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if match not in pricing_info:
                        pricing_info.append(match)
        
        return pricing_info
    
    def extract_services_from_text(self, text: str) -> List[str]:
        services = []
        service_keywords = [
            'roof repair', 'roof replacement', 'roof installation',
            'shingle', 'metal roof', 'tile roof', 'flat roof',
            'gutter', 'siding', 'leak repair', 'storm damage',
            'insurance claims', 'emergency repair', 'inspection',
            'maintenance', 'ventilation', 'skylight'
        ]
        
        text_lower = text.lower()
        for keyword in service_keywords:
            if keyword in text_lower:
                services.append(keyword.title())
        
        return list(set(services))
    
    def analyze_review_keywords(self, reviews: List[Dict]) -> Tuple[List[str], List[str], Dict[str, int]]:
        all_text = ' '.join([review.get('text', '').lower() for review in reviews])
        
        positive_found = [keyword for keyword in self.positive_indicators if keyword in all_text]
        negative_found = [keyword for keyword in self.negative_indicators if keyword in all_text]
        
        themes = {}
        for theme, keywords in self.opportunity_keywords.items():
            count = sum(all_text.count(keyword) for keyword in keywords)
            if count > 0:
                themes[theme] = count
        
        return positive_found, negative_found, themes
    
    def analyze_competitors(self, your_address: str, radius_miles: int = 5) -> List[Competitor]:
        # Get coordinates for your address
        your_lat, your_lng = self.geocode_address(your_address)
        
        # Search for nearby roofing companies
        places = self.search_nearby_roofing_companies(your_lat, your_lng, radius_miles)
        
        competitors = []
        
        for place in places:
            details = self.get_place_details(place['place_id'])
            
            if not details:
                continue
            
            # Calculate distance
            place_lat = place['geometry']['location']['lat']
            place_lng = place['geometry']['location']['lng']
            distance = geodesic((your_lat, your_lng), (place_lat, place_lng)).miles
            
            # Extract data
            reviews = details.get('reviews', [])
            pricing_info = self.extract_pricing_from_reviews(reviews)
            all_text = ' '.join([review.get('text', '') for review in reviews])
            services = self.extract_services_from_text(all_text + ' ' + details.get('name', ''))
            positive_keywords, negative_keywords, review_themes = self.analyze_review_keywords(reviews)
            
            competitor = Competitor(
                name=details.get('name', 'Unknown'),
                address=details.get('formatted_address', 'Unknown'),
                phone=details.get('formatted_phone_number', 'Not available'),
                rating=details.get('rating', 0.0),
                review_count=details.get('user_ratings_total', 0),
                website=details.get('website', 'Not available'),
                distance_miles=round(distance, 2),
                pricing_info=pricing_info,
                services=services,
                positive_keywords=positive_keywords,
                negative_keywords=negative_keywords,
                review_themes=review_themes
            )
            
            competitors.append(competitor)
            time.sleep(0.1)  # Reduced from 0.5 to 0.1 seconds
        
        # Sort by distance
        competitors.sort(key=lambda x: x.distance_miles)
        
        return competitors

def create_competitor_dataframe(competitors: List[Competitor]) -> pd.DataFrame:
    """Convert competitors to DataFrame for display"""
    data = []
    for comp in competitors:
        # Format review themes with counts
        themes_formatted = '; '.join([f"{theme}({count})" for theme, count in list(comp.review_themes.items())[:5]])
        
        data.append({
            'Company': comp.name,
            'Distance (mi)': comp.distance_miles,
            'Rating': comp.rating,
            'Reviews': comp.review_count,
            'Phone': comp.phone,
            'Website': comp.website if comp.website != 'Not available' else 'N/A',
            'Services': '; '.join(comp.services) if comp.services else 'Services not specified',
            'Pricing Info': '; '.join(comp.pricing_info) if comp.pricing_info else 'No pricing found',
            'Positive Keywords': '; '.join(comp.positive_keywords[:10]) if comp.positive_keywords else 'None found',
            'Negative Keywords': '; '.join(comp.negative_keywords[:10]) if comp.negative_keywords else 'None found',
            'Review Themes': themes_formatted if themes_formatted else 'No themes identified',
            'Pricing Found': 'Yes' if comp.pricing_info else 'No',
            'Top Complaints': '; '.join(comp.negative_keywords[:3]) if comp.negative_keywords else 'None'
        })
    return pd.DataFrame(data)

def main():
    # Header
    st.title("🏠 Roofing Competitor Analyzer")
    st.markdown("### Analyze your local competition and discover market opportunities")
    
    # Sidebar for inputs
    st.sidebar.header("📍 Analysis Settings")
    
    # User inputs
    address = st.sidebar.text_input(
        "Business Address",
        placeholder="123 Main St, City, State ZIP",
        help="Enter your business address to find nearby competitors"
    )
    
    radius = st.sidebar.slider(
        "Search Radius (miles)",
        min_value=1,
        max_value=25,
        value=5,
        help="How far to search for competitors"
    )
    
    # Analyze button
    if st.sidebar.button("🔍 Analyze Competition", type="primary"):
        if not address:
            st.error("Please enter a business address")
            return
        
        # Initialize analyzer
        analyzer = RoofingCompetitorAnalyzer(GOOGLE_API_KEY)
        
        # Show loading
        # Show loading with progress
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner(f"🔎 Searching for roofing competitors within {radius} miles..."):
            try:
                # Initialize analyzer
                analyzer = RoofingCompetitorAnalyzer(GOOGLE_API_KEY)
                
                # Get initial search results
                status_text.text("📍 Finding your location...")
                progress_bar.progress(10)
                
                your_lat, your_lng = analyzer.geocode_address(address)
                
                status_text.text("🔍 Searching for competitors...")
                progress_bar.progress(25)
                
                places = analyzer.search_nearby_roofing_companies(your_lat, your_lng, radius)
                
                if not places:
                    st.warning("No competitors found. Try expanding your search radius.")
                    return
                
                # Process competitors with progress updates
                competitors = []
                total_places = len(places)
                
                for i, place in enumerate(places):
                    progress = 25 + (i / total_places) * 70  # 25% to 95%
                    progress_bar.progress(int(progress))
                    status_text.text(f"📊 Analyzing competitor {i+1}/{total_places}: {place.get('name', 'Unknown')}")
                    
                    details = analyzer.get_place_details(place['place_id'])
                    
                    if not details:
                        continue
                    
                    # Calculate distance
                    place_lat = place['geometry']['location']['lat']
                    place_lng = place['geometry']['location']['lng']
                    distance = geodesic((your_lat, your_lng), (place_lat, place_lng)).miles
                    
                    # Extract data
                    reviews = details.get('reviews', [])
                    pricing_info = analyzer.extract_pricing_from_reviews(reviews)
                    all_text = ' '.join([review.get('text', '') for review in reviews])
                    services = analyzer.extract_services_from_text(all_text + ' ' + details.get('name', ''))
                    positive_keywords, negative_keywords, review_themes = analyzer.analyze_review_keywords(reviews)
                    
                    competitor = Competitor(
                        name=details.get('name', 'Unknown'),
                        address=details.get('formatted_address', 'Unknown'),
                        phone=details.get('formatted_phone_number', 'Not available'),
                        rating=details.get('rating', 0.0),
                        review_count=details.get('user_ratings_total', 0),
                        website=details.get('website', 'Not available'),
                        distance_miles=round(distance, 2),
                        pricing_info=pricing_info,
                        services=services,
                        positive_keywords=positive_keywords,
                        negative_keywords=negative_keywords,
                        review_themes=review_themes
                    )
                    
                    competitors.append(competitor)
                    time.sleep(0.1)  # Reduced delay
                
                # Sort by distance
                competitors.sort(key=lambda x: x.distance_miles)
                
                progress_bar.progress(100)
                status_text.text("✅ Analysis complete!")
                time.sleep(1)
                progress_bar.empty()
                status_text.empty()
                
                # Store results in session state
                st.session_state.competitors = competitors
                st.session_state.address = address
                st.session_state.radius = radius
                
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"Error during analysis: {str(e)}")
                st.info("Make sure your address is valid and try again.")
                return
    
    # Display results if available
    if 'competitors' in st.session_state:
        competitors = st.session_state.competitors
        
        st.success(f"✅ Found {len(competitors)} competitors near {st.session_state.address}")
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Competitors", len(competitors))
        
        with col2:
            avg_rating = sum(c.rating for c in competitors if c.rating > 0) / len([c for c in competitors if c.rating > 0])
            st.metric("Avg Rating", f"{avg_rating:.1f}⭐")
        
        with col3:
            total_reviews = sum(c.review_count for c in competitors)
            st.metric("Total Reviews", f"{total_reviews:,}")
        
        with col4:
            closest = min(competitors, key=lambda x: x.distance_miles)
            st.metric("Closest Competitor", f"{closest.distance_miles:.1f} mi")
        
        # Tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "🏢 Competitors", "💡 Opportunities", "📈 Analytics"])
        
        with tab1:
            st.subheader("Competition Overview")
            
            # Create DataFrame
            df = create_competitor_dataframe(competitors)
            st.dataframe(df, use_container_width=True)
            
            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download Full Report (CSV)",
                data=csv,
                file_name=f"competitor_analysis_{int(time.time())}.csv",
                mime="text/csv"
            )
        
        with tab2:
            st.subheader("Detailed Competitor Profiles")
            
            for i, comp in enumerate(competitors[:10]):  # Show top 10
                with st.expander(f"{comp.name} - {comp.distance_miles} mi away"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**📍 Address:** {comp.address}")
                        st.write(f"**📞 Phone:** {comp.phone}")
                        st.write(f"**⭐ Rating:** {comp.rating}/5 ({comp.review_count} reviews)")
                        if comp.website != 'Not available':
                            st.write(f"**🌐 Website:** [Visit]({comp.website})")
                    
                    with col2:
                        if comp.services:
                            st.write("**🔧 Services:**")
                            for service in comp.services[:5]:
                                st.write(f"• {service}")
                        
                        if comp.pricing_info:
                            st.write("**💰 Pricing Mentions:**")
                            for price in comp.pricing_info[:3]:
                                st.write(f"• {price}")
                    
                    if comp.negative_keywords:
                        st.write("**⚠️ Common Complaints:**")
                        st.write(", ".join(comp.negative_keywords[:5]))
        
        with tab3:
            st.subheader("Market Opportunities")
            
            # Collect all negative keywords
            all_negatives = []
            all_themes = Counter()
            
            for comp in competitors:
                all_negatives.extend(comp.negative_keywords)
                for theme, count in comp.review_themes.items():
                    all_themes[theme] += count
            
            negative_counter = Counter(all_negatives)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🚨 Most Common Complaints")
                if negative_counter:
                    for complaint, count in negative_counter.most_common(10):
                        st.write(f"• **{complaint}** (mentioned {count} times)")
                    st.info("💡 Focus on these areas to differentiate your business!")
                else:
                    st.write("No significant complaints found in reviews.")
            
            with col2:
                st.subheader("📈 Review Themes")
                if all_themes:
                    theme_data = dict(all_themes.most_common(8))
                    fig = px.bar(
                        x=list(theme_data.values()),
                        y=list(theme_data.keys()),
                        orientation='h',
                        title="What Customers Talk About Most"
                    )
                    fig.update_layout(height=400)
                    st.plotly_chart(fig, use_container_width=True)
            
            # Service gap analysis
            st.subheader("🎯 Service Gaps")
            all_services = []
            for comp in competitors:
                all_services.extend(comp.services)
            
            service_counter = Counter(all_services)
            total_competitors = len(competitors)
            
            gaps = []
            for service, count in service_counter.items():
                if count / total_competitors < 0.3:
                    gaps.append(f"{service} (only {count}/{total_competitors} competitors offer this)")
            
            if gaps:
                st.write("**Underserved services in your market:**")
                for gap in gaps[:5]:
                    st.write(f"• {gap}")
            else:
                st.write("No significant service gaps identified.")
        
        with tab4:
            st.subheader("Competition Analytics")
            
            # Rating distribution
            col1, col2 = st.columns(2)
            
            with col1:
                ratings = [c.rating for c in competitors if c.rating > 0]
                fig = px.histogram(
                    x=ratings,
                    nbins=10,
                    title="Competitor Rating Distribution"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Distance vs Rating scatter
                distances = [c.distance_miles for c in competitors if c.rating > 0]
                ratings = [c.rating for c in competitors if c.rating > 0]
                names = [c.name for c in competitors if c.rating > 0]
                
                fig = px.scatter(
                    x=distances,
                    y=ratings,
                    hover_name=names,
                    title="Distance vs Rating",
                    labels={'x': 'Distance (miles)', 'y': 'Rating'}
                )
                st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()