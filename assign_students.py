"""
Assign Existing Students to Schools
Run this to assign students who registered before school selection was added
"""

import psycopg2

DATABASE_URL = ""

def list_unassigned_students():
    """Show all students without a school"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, full_name, email, grade_band, created_at
            FROM users 
            WHERE role = 'student' AND (school IS NULL OR school = '')
            ORDER BY created_at DESC
        """)
        
        students = cursor.fetchall()
        
        print("\n📋 Students Without School Assignment:")
        print("-" * 100)
        print(f"{'ID':<5} {'Name':<30} {'Email':<35} {'Grade':<15} {'Joined':<15}")
        print("-" * 100)
        
        for student in students:
            student_id, name, email, grade, created_at = student
            created_str = str(created_at)[:10] if created_at else 'Unknown'
            print(f"{student_id:<5} {name:<30} {email:<35} {grade or 'N/A':<15} {created_str:<15}")
        
        print("-" * 100)
        print(f"Total unassigned students: {len(students)}\n")
        
        cursor.close()
        conn.close()
        
        return students
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def assign_student_to_school(student_id, school):
    """Assign a student to a specific school"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Verify student exists
        cursor.execute("""
            SELECT full_name, email 
            FROM users 
            WHERE id = %s AND role = 'student'
        """, (student_id,))
        
        student = cursor.fetchone()
        if not student:
            print(f"❌ No student found with ID {student_id}")
            cursor.close()
            conn.close()
            return False
        
        name, email = student
        
        # Update school
        cursor.execute("""
            UPDATE users 
            SET school = %s 
            WHERE id = %s
        """, (school, student_id))
        
        conn.commit()
        
        print(f"✅ Assigned {name} ({email}) to {school}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def bulk_assign_by_ids(student_ids, school):
    """Assign multiple students by ID list"""
    print(f"\n🔄 Bulk assigning {len(student_ids)} students to {school}...")
    
    success_count = 0
    for student_id in student_ids:
        if assign_student_to_school(student_id, school):
            success_count += 1
    
    print(f"\n✅ Successfully assigned {success_count}/{len(student_ids)} students to {school}")

def bulk_assign_by_email_domain(email_pattern, school):
    """Assign students based on email pattern"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, full_name, email
            FROM users 
            WHERE role = 'student' 
            AND (school IS NULL OR school = '')
            AND email LIKE %s
        """, (f'%{email_pattern}%',))
        
        students = cursor.fetchall()
        
        print(f"\n📧 Found {len(students)} students with email containing '{email_pattern}':")
        
        if len(students) == 0:
            print("No students found with that email pattern.")
            cursor.close()
            conn.close()
            return
        
        for student in students:
            print(f"  - {student[1]} ({student[2]})")
        
        confirm = input(f"\nAssign all {len(students)} students to {school}? (y/n): ")
        
        if confirm.lower() == 'y':
            cursor.execute("""
                UPDATE users 
                SET school = %s 
                WHERE role = 'student' 
                AND (school IS NULL OR school = '')
                AND email LIKE %s
            """, (school, f'%{email_pattern}%'))
            
            conn.commit()
            print(f"✅ Assigned {len(students)} students to {school}")
        else:
            print("Cancelled.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

def interactive_assignment():
    """Interactive mode to assign students"""
    print("\n" + "="*100)
    print("STUDENT SCHOOL ASSIGNMENT")
    print("="*100)
    
    students = list_unassigned_students()
    
    if not students:
        print("\n✅ All students are already assigned to schools!")
        return
    
    print("\nAvailable schools:")
    print("  1. McMain")
    print("  2. Columbia")
    
    print("\nAssignment methods:")
    print("  [1] Assign individual students (enter ID)")
    print("  [2] Bulk assign by student IDs")
    print("  [3] Bulk assign by email pattern")
    print("  [q] Quit")
    
    choice = input("\nSelect method: ").strip()
    
    if choice == '1':
        # Individual assignment
        while True:
            student_id = input("\nEnter Student ID to assign (or 'q' to quit): ").strip()
            
            if student_id.lower() == 'q':
                break
            
            try:
                student_id = int(student_id)
            except ValueError:
                print("❌ Invalid ID. Please enter a number.")
                continue
            
            school_choice = input("Select school (1=McMain, 2=Columbia): ").strip()
            
            if school_choice == '1':
                school = 'McMain'
            elif school_choice == '2':
                school = 'Columbia'
            else:
                print("❌ Invalid choice. Please enter 1 or 2.")
                continue
            
            assign_student_to_school(student_id, school)
    
    elif choice == '2':
        # Bulk by IDs
        ids_input = input("\nEnter student IDs separated by commas (e.g., 10,11,12): ").strip()
        school_choice = input("Assign to (1=McMain, 2=Columbia): ").strip()
        
        school = 'McMain' if school_choice == '1' else 'Columbia'
        
        try:
            student_ids = [int(x.strip()) for x in ids_input.split(',')]
            bulk_assign_by_ids(student_ids, school)
        except ValueError:
            print("❌ Invalid input. Please enter comma-separated numbers.")
    
    elif choice == '3':
        # Bulk by email pattern
        email_pattern = input("\nEnter email pattern (e.g., '@mcmain.org'): ").strip()
        school_choice = input("Assign to (1=McMain, 2=Columbia): ").strip()
        
        school = 'McMain' if school_choice == '1' else 'Columbia'
        bulk_assign_by_email_domain(email_pattern, school)
    
    # Show final results
    print("\n" + "="*100)
    print("REMAINING UNASSIGNED STUDENTS")
    print("="*100)
    list_unassigned_students()

def show_school_distribution():
    """Show current distribution of students by school"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COALESCE(school, 'Unassigned') as school_name,
                COUNT(*) as student_count
            FROM users 
            WHERE role = 'student'
            GROUP BY school
            ORDER BY school_name
        """)
        
        results = cursor.fetchall()
        
        print("\n📊 Student Distribution by School:")
        print("-" * 50)
        for school, count in results:
            print(f"{school:<20} {count:>5} students")
        print("-" * 50)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'stats':
        show_school_distribution()
    else:
        show_school_distribution()
        interactive_assignment()