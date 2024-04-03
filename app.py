from flask import Flask, jsonify, request
import cachelib
import requests
from bs4 import BeautifulSoup
import re
import numpy as np
import json

app = Flask(__name__)
cache = cachelib.SimpleCache()  # Configure a simple in-memory cache


class ContainerLocator:
    URL = "https://inzameling.spaarnelanden.nl/"
    EARTH_RADIUS_KM = 6373.0  # Approximate radius of earth in km

    def fetch_script_data(self):
        # Check if cached data is available
        cached_data = cache.get('script_data')
        if cached_data:
            return None, cached_data

        # If not cached, fetch the data
        try:
            data = requests.get(self.URL).content.decode("utf-8")
            soup = BeautifulSoup(data, "html.parser")
            pattern = re.compile(r"districts|oContainerModel = '(.*?)';$", re.MULTILINE | re.DOTALL)
            script = soup.find("script", string=pattern)

            if not script:
                return "Script matching pattern not found.", None

            # Cache the fetched data for 300 seconds (5 minutes)
            cache.set('script_data', script.text, timeout=300)
            return None, script.text

        except requests.RequestException as e:
            return f"Error fetching data: {e}", None

    def extract_data(self, script_data):
        data = {}
        variables = re.findall(re.compile(r"(districts|oContainerModel) = (\[.*?\])", re.MULTILINE | re.DOTALL), script_data)
        for key, value in variables:
            if value != '[]':
                data[key] = json.loads(value)
        return data.get("districts", []), data.get("oContainerModel", [])

    def find_coordinates(self, containers, container_id):
        for container in containers:
            if container.get("sRegistrationNumber") == str(container_id):
                return container.get("dLatitude"), container.get("dLongitude")
        return None, None

    def containers_within_radius(self, containers, center, radius=1):
        def calculate_distance(center, targets):
            s_lat, s_lng = np.radians(center)
            e_lat, e_lng, ids = zip(*[(np.radians(lat), np.radians(lng), id) for lat, lng, id in targets])
            
            d = np.sin((e_lat - s_lat)/2)**2 + np.cos(s_lat)*np.cos(e_lat) * np.sin((e_lng - s_lng)/2)**2
            return zip(ids, 2 * self.EARTH_RADIUS_KM * np.arcsin(np.sqrt(d)))
        
        target_data = [(container.get("dLatitude"), container.get("dLongitude"), container.get("sRegistrationNumber"))
                       for container in containers]
        for container_id, distance_km in calculate_distance(center, target_data):  # Ensure both arguments are passed
            if distance_km <= radius:                
                container_details = next((item for item in containers if item["sRegistrationNumber"] == container_id), None)
                if container_details:
                    yield {
                        "sRegistrationNumber": container_id,
                        "distance": distance_km,
                        "dFillingDegree": container_details.get("dFillingDegree"),
                        "sDateLastEmptied": container_details.get("sDateLastEmptied"),
                        "bIsEmptiedToday": container_details.get("bIsEmptiedToday"),
                        "sProductName": container_details.get("sProductName")
                    }


    def main(self, container_id, radius):
        script_data = self.fetch_script_data()
        if script_data:
            _, containers = self.extract_data(script_data)
            lat, lng = self.find_coordinates(containers, container_id)
            if lat and lng:
                for container in self.containers_within_radius(containers, (lat, lng), radius=radius):
                    print(container)

@app.route('/find_containers', methods=['GET'])
def find_containers():
    container_id = request.args.get('center', type=int)
    radius = request.args.get('radius', default=0.15, type=float)

    if not container_id:
        return jsonify({"error": "Parameter 'center' (containerId) is required"}), 400

    locator = ContainerLocator()
    _, script_data = locator.fetch_script_data()
    if script_data:
        _, containers = locator.extract_data(script_data)
        lat, lng = locator.find_coordinates(containers, container_id)
        if lat and lng:
            nearby_containers = list(locator.containers_within_radius(containers, (lat, lng), radius=radius))
            return jsonify(nearby_containers)
        else:
            return jsonify({"error": "Container not found"}), 404
    else:
        return jsonify({"error": "Failed to fetch or parse script data"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
