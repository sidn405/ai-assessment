// Add to dashboard.js

async function displayUserLexileLevel() {
    try {
        const response = await fetch('/api/user/lexile-info', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Update UI with Lexile info
            document.getElementById('userLevel').innerHTML = `
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div>
                        <strong style="font-size: 24px; color: #1e40af;">${data.lexile_level}L</strong>
                        <div style="font-size: 12px; color: #6b7280;">${data.lexile_label}</div>
                    </div>
                    <div style="flex: 1; background: #e5e7eb; height: 8px; border-radius: 4px; overflow: hidden;">
                        <div style="width: ${(data.lexile_level / 1600) * 100}%; height: 100%; background: linear-gradient(90deg, #3b82f6, #1e40af); transition: width 0.3s;"></div>
                    </div>
                </div>
            `;
            
            // Show target Lexile
            if (data.target_lexile) {
                document.getElementById('targetLevel').textContent = `Target: ${data.target_lexile}L`;
            }
        }
    } catch (error) {
        console.error('Error fetching Lexile info:', error);
    }
}

// Call on page load
window.addEventListener('load', displayUserLexileLevel);