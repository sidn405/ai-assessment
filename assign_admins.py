"""
Assign Admins to Schools
Run this after migration to assign existing admins to their schools
"""

import psycopg2

# Your database URL
DATABASE_URL = ""

def list_admins():
    """Show all current admin users"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, full_name, email, school
            FROM users 
            WHERE role = 'admin'
            ORDER BY id
        """)
        
        admins = cursor.fetchall()
        
        print("\n📋 Current Admin Users:")
        print("-" * 80)
        print(f"{'ID':<5} {'Name':<25} {'Email':<30} {'School':<15}")
        print("-" * 80)
        
        for admin in admins:
            admin_id, name, email, school = admin
            school_display = school if school else "Not assigned"
            print(f"{admin_id:<5} {name:<25} {email:<30} {school_display:<15}")
        
        print("-" * 80)
        
        cursor.close()
        conn.close()
        
        return admins
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def assign_admin_to_school(admin_id, school):
    """Assign an admin to a specific school"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Verify admin exists
        cursor.execute("""
            SELECT full_name, email 
            FROM users 
            WHERE id = %s AND role = 'admin'
        """, (admin_id,))
        
        admin = cursor.fetchone()
        if not admin:
            print(f"❌ No admin found with ID {admin_id}")
            cursor.close()
            conn.close()
            return False
        
        name, email = admin
        
        # Update school
        cursor.execute("""
            UPDATE users 
            SET school = %s 
            WHERE id = %s
        """, (school, admin_id))
        
        conn.commit()
        
        print(f"✅ Assigned {name} ({email}) to {school}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def interactive_assignment():
    """Interactive mode to assign admins"""
    print("\n" + "="*80)
    print("ADMIN SCHOOL ASSIGNMENT")
    print("="*80)
    
    admins = list_admins()
    
    if not admins:
        print("\n⚠️  No admins found!")
        return
    
    print("\nAvailable schools:")
    print("  1. McMain")
    print("  2. Columbia")
    print("  3. None (Super Admin - sees all schools)")
    
    while True:
        print("\n" + "-"*80)
        admin_id = input("\nEnter Admin ID to assign (or 'q' to quit): ").strip()
        
        if admin_id.lower() == 'q':
            break
        
        try:
            admin_id = int(admin_id)
        except ValueError:
            print("❌ Invalid ID. Please enter a number.")
            continue
        
        school_choice = input("Select school (1=McMain, 2=Columbia, 3=None): ").strip()
        
        if school_choice == '1':
            school = 'McMain'
        elif school_choice == '2':
            school = 'Columbia'
        elif school_choice == '3':
            school = None
        else:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")
            continue
        
        assign_admin_to_school(admin_id, school)
    
    print("\n" + "="*80)
    print("FINAL ADMIN ASSIGNMENTS")
    print("="*80)
    list_admins()

def quick_assign():
    """Quick assignment based on known admin IDs"""
    print("\n" + "="*80)
    print("QUICK ASSIGNMENT MODE")
    print("="*80)
    print("\nEdit this script to set your admin IDs and schools, then run:")
    print("""
# Example:
assign_admin_to_school(1, 'McMain')      # Admin ID 1 → Mc Main
assign_admin_to_school(2, 'Columbia')    # Admin ID 2 → Columbia
assign_admin_to_school(3, None)          # Admin ID 3 → Super Admin
    """)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'quick':
        quick_assign()
    else:
        interactive_assignment()