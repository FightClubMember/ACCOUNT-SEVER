import secrets

# Character pools
UPPERCASE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWERCASE = "abcdefghijklmnopqrstuvwxyz"
NUMBERS = "0123456789"
SYMBOLS = "!@#$%^&*()_+-=[]{}<>?"

def generate_secure_password(
    length: int = 16,
    use_symbols: bool = True,
    use_uppercase: bool = True,
    use_lowercase: bool = True,
    use_numbers: bool = True
) -> str:
    """
    Generates a cryptographically secure random password based on the configuration.
    Uses the python secrets module and ensures no simple repeating patterns (e.g., aaa).
    """
    # Enforce minimum length
    length = max(length, 8)
    
    # Map toggles to their respective pools
    pools = []
    if use_uppercase:
        pools.append(UPPERCASE)
    if use_lowercase:
        pools.append(LOWERCASE)
    if use_numbers:
        pools.append(NUMBERS)
    if use_symbols:
        pools.append(SYMBOLS)
        
    # Fallback to prevent crashing if all options are disabled
    if not pools:
        pools = [LOWERCASE, NUMBERS]
        
    # Combine pools for general selection
    all_chars = "".join(pools)
    
    # Try generating until we pass pattern checks (max 50 attempts)
    for _ in range(50):
        password_chars = []
        
        # 1. Guarantee at least one character from each enabled pool
        for pool in pools:
            password_chars.append(secrets.choice(pool))
            
        # 2. Fill the remaining length from the general pool
        remaining_length = length - len(password_chars)
        for _ in range(remaining_length):
            password_chars.append(secrets.choice(all_chars))
            
        # 3. Cryptographically secure shuffle of the selected characters
        # Sort based on random float/bits to avoid importing the forbidden 'random' module
        shuffled = sorted(password_chars, key=lambda _: secrets.randbits(64))
        password = "".join(shuffled)
        
        # 4. Check for repeated predictable patterns (triple repeating chars e.g. "aaa")
        has_pattern = False
        for i in range(len(password) - 2):
            if password[i] == password[i+1] == password[i+2]:
                has_pattern = True
                break
                
        if not has_pattern:
            return password
            
    # Fallback if pattern check repeatedly fails
    return "".join(sorted(password_chars, key=lambda _: secrets.randbits(64)))
