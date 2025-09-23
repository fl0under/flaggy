#!/usr/bin/env python3
import hashlib
import base64

# Hidden flag in base64
hidden_flag = "cGljb0NURntweXRoMG5fY29kZV9hbjRseXNpc19za2lsbHN9"

def check_password(password):
    """Check if password is correct"""
    # Vulnerable: hardcoded hash comparison
    expected_hash = "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
    actual_hash = hashlib.sha256(password.encode()).hexdigest()
    return actual_hash == expected_hash

def reveal_flag():
    """Decode and return the flag"""
    try:
        flag = base64.b64decode(hidden_flag).decode('utf-8')
        return flag
    except:
        return "Error decoding flag"

def main():
    print("Source Analysis Challenge")
    print("Find the correct password by analyzing the code!")
    
    password = input("Enter password: ")
    
    if check_password(password):
        print("Correct!")
        print(f"Flag: {reveal_flag()}")
    else:
        print("Wrong password!")

if __name__ == "__main__":
    main()