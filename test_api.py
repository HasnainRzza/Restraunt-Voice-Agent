import time
import subprocess
import httpx
import sys

def main():
    print("🚀 Starting API Verification Tests...", flush=True)
    
    # 1. Start the FastAPI server in a background subprocess
    # We let stdout/stderr inherit so the process doesn't block on buffered pipes on Windows
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=script_dir
    )
    
    # Wait for server to boot (give it 5 seconds)
    print("⏳ Waiting for Uvicorn server to start...")
    time.sleep(5)
    
    # Verify if process is still running
    if server_process.poll() is not None:
        print("❌ Server failed to start immediately.")
        sys.exit(1)
        
    client = httpx.Client(base_url="http://127.0.0.1:8000")
    
    try:
        # Generate a unique email for every test run
        test_email = f"staff_{int(time.time())}@hotbagels.com"
        
        # 2. Test Signup
        print("\n🔹 Testing /api/auth/signup...")
        signup_res = client.post(
            "/api/auth/signup",
            json={
                "email": test_email,
                "password": "securepassword123",
                "display_name": "Bagel Manager"
            }
        )
        assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
        signup_data = signup_res.json()
        otp_code = signup_data.get("otp_code")
        print(f"✅ Signup successful! Received Mock OTP: {otp_code}")
        
        # 3. Test Verify OTP
        print("\n🔹 Testing /api/auth/verify-otp...")
        verify_res = client.post(
            "/api/auth/verify-otp",
            json={
                "email": test_email,
                "otp": otp_code
            }
        )
        assert verify_res.status_code == 200, f"Verify OTP failed: {verify_res.text}"
        print("✅ OTP Verification successful! Account activated.")
        
        # 4. Test Login
        print("\n🔹 Testing /api/auth/login...")
        login_res = client.post(
            "/api/auth/login",
            json={
                "email": test_email,
                "password": "securepassword123"
            }
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        login_data = login_res.json()
        auth_token = login_data["access_token"]
        print("✅ Login successful! Received Auth Token.")
        
        # Add Authorization Header
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # 5. Test Webhook Call Start
        print("\n🔹 Testing /webhook/call/start...")
        start_res = client.post(
            "/webhook/call/start",
            json={"caller_id": "+15550199"}
        )
        assert start_res.status_code == 200, f"Start call failed: {start_res.text}"
        session_id = start_res.json()["session_id"]
        print(f"✅ Webhook Call Started! Session ID: {session_id}")
        
        # 6. Test Webhook Call Audio (Mock Silent WAV)
        print("\n🔹 Testing /webhook/call/audio...")
        # Create a tiny 1-second silence or empty request body
        audio_res = client.post(
            f"/webhook/call/audio?session_id={session_id}",
            content=b""
        )
        assert audio_res.status_code == 200, f"Process call audio failed: {audio_res.text}"
        print(f"✅ Webhook Call Audio processed! Received {len(audio_res.content)} bytes of synthesized agent audio.")
        
        # 7. Test Webhook Call End
        print("\n🔹 Testing /webhook/call/end...")
        end_res = client.post(
            "/webhook/call/end",
            json={"session_id": session_id}
        )
        assert end_res.status_code == 200, f"End call failed: {end_res.text}"
        print("✅ Webhook Call Ended! Data persisted.")
        
        # 8. Test Paginated Call List (JWT Protected)
        print("\n🔹 Testing /api/calls (JWT protected)...")
        list_res = client.get("/api/calls?page=1&limit=5", headers=headers)
        assert list_res.status_code == 200, f"List calls failed: {list_res.text}"
        list_data = list_res.json()
        print(f"✅ Paginated calls list retrieved successfully! Total calls in DB: {list_data['total_calls']}")
        assert len(list_data["calls"]) > 0, "No calls returned in paginated list"
        
        # 9. Test Single Call Detail (JWT Protected)
        print(f"\n🔹 Testing /api/calls/{session_id} (JWT protected)...")
        detail_res = client.get(f"/api/calls/{session_id}", headers=headers)
        assert detail_res.status_code == 200, f"Get call details failed: {detail_res.text}"
        detail_data = detail_res.json()
        print("✅ Call session details retrieved successfully!")
        assert detail_data["caller_id"] == "+15550199", "Caller ID mismatch"
        
        print("\n🎉 ALL API ENDPOINT TESTS PASSED SUCCESSFULLY! 🎉", flush=True)
        
    except AssertionError as ae:
        print(f"\n❌ Assertion failed: {ae}", flush=True)
    except Exception as e:
        print(f"\n❌ Test failed: {e}", flush=True)
    finally:
        # 10. Clean up server process
        print("\n🛑 Shutting down Uvicorn test server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
            print("✅ Server shutdown cleanly.")
        except subprocess.TimeoutExpired:
            server_process.kill()
            print("⚠️ Server killed forcefully.")

if __name__ == "__main__":
    main()
