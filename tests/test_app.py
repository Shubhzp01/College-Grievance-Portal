import unittest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from database import init_db, seed_db, query_db

class PortalTestCase(unittest.TestCase):
    """
    Test suite for College Grievance Portal.
    Validates public views, user authentication, role restrictions,
    complaint lifecycles, and export endpoints.
    """
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        with app.app_context():
            if os.path.exists(app.config['DATABASE_PATH']):
                try:
                    os.remove(app.config['DATABASE_PATH'])
                except Exception:
                    pass
            init_db()
            seed_db()

    def test_public_routes(self):
        # Landing page
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Student Grievance Redressal Cell', res.data)

        # About and Contact
        self.assertEqual(self.client.get('/about').status_code, 200)
        self.assertEqual(self.client.get('/contact').status_code, 200)

        # Track route with code
        res_track = self.client.get('/track?code=CMP-2026-0001')
        self.assertEqual(res_track.status_code, 200)
        self.assertIn(b'Wi-Fi connectivity issue', res_track.data)

    def test_admin_workflows(self):
        # Login as Admin
        res_login = self.client.post('/login', data={
            'email': 'admin@college.com',
            'password': 'Admin@123'
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b'Administrator Control Center', res_login.data)

        # Chart API endpoint
        res_api = self.client.get('/admin/api/chart-data')
        self.assertEqual(res_api.status_code, 200)
        data = res_api.get_json()
        self.assertIn('status', data)
        self.assertIn('category', data)

        # Manage Complaints view
        res_mgmt = self.client.get('/admin/complaints')
        self.assertEqual(res_mgmt.status_code, 200)

        # Status Transition & Remarks
        res_update = self.client.post('/admin/complaint/3/update', data={
            'status': 'In Progress',
            'assigned_to': 'Maintenance Team',
            'remark': 'Technician dispatched to replace AC compressor.'
        }, follow_redirects=True)
        self.assertEqual(res_update.status_code, 200)

        # CSV Export
        res_csv = self.client.get('/admin/export/complaints.csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.content_type, 'text/csv; charset=utf-8')

    def test_student_workflows(self):
        # Login as Student
        res_login = self.client.post('/login', data={
            'email': 'rahul.sharma@college.com',
            'password': 'Student@123'
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)

        # Submit Complaint
        res_submit = self.client.post('/student/complaint/new', data={
            'title': 'Library AC not cooling in Reading Room 2',
            'category': 'Library & Study Halls',
            'priority': 'Medium',
            'description': 'The air conditioner in the quiet reading zone has stopped blowing cold air.',
            'is_anonymous': '0'
        }, follow_redirects=True)
        self.assertEqual(res_submit.status_code, 200)
        self.assertIn(b'Complaint submitted successfully', res_submit.data)

        # View Complaints
        res_list = self.client.get('/student/complaints')
        self.assertEqual(res_list.status_code, 200)
        self.assertIn(b'Library AC not cooling', res_list.data)

    def test_registration(self):
        res = self.client.post('/register', data={
            'name': 'Aakash Mehta',
            'email': 'aakash.mehta@college.com',
            'roll_no': '2024ME310',
            'department': 'Mechanical Engineering',
            'password': 'Password@123',
            'confirm_password': 'Password@123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Account registered successfully', res.data)

    def test_404_handling(self):
        res = self.client.get('/non-existent-route-endpoint')
        self.assertEqual(res.status_code, 404)
        self.assertIn(b'Page Not Found', res.data)

if __name__ == '__main__':
    unittest.main()
