
import json
import uuid

from locust import HttpUser, between, task


class APIUser(HttpUser):
    # Wait between 1 and 3 seconds between tasks
    wait_time = between(1, 3)
    
    def on_start(self):
        """
        Called when a Locust user starts.
        Loads the reservation payload from the JSON file.
        """
        with open('crear_reserva.json') as f:
            self.payload = json.load(f)

    @task
    def create_reservation(self):
        """
        Task to simulate creating a reservation.
        It sends a POST request to the /api/v1/reservations endpoint.
        A unique Idempotency-Key is generated for each request.
        """
        headers = {
            "Idempotency-Key": str(uuid.uuid4()),
            "Content-Type": "application/json"
        }
        self.client.post(
            "/api/v1/reservations",
            json=self.payload,
            headers=headers,
            name="/api/v1/reservations" # Group all requests under this name in the stats
        )
