import os
import time
import requests
import gradio as gr
import openstack
from openstack import exceptions

# --- CONFIGURATION & SHARED STATE ---
active_user_count = 0
is_dekcib_alive = False
domain_name = "dekcib-production.cis260093.projects.jetstream-cloud.org"
full_url = f"https://{domain_name}"

# Dynamic HTML link generator
def get_flashing_link(url):
    return f"""
<style>
@keyframes flash {{
    0% {{ opacity: 1; }}
    50% {{ opacity: 0.4; }}
    100% {{ opacity: 1; }}
}}
.flashing-btn {{
    display: inline-block;
    padding: 30px 60px;
    font-size: 32px;
    font-weight: 900;
    text-decoration: none;
    color: black !important;
    background-color: #39FF14;
    border: 6px solid black;
    border-radius: 8px;
    text-align: center;
    animation: flash 1s infinite;
    box-shadow: 0 0 30px #39FF14;
    transition: transform 0.2s;
}}
.flashing-btn:hover {{
    animation: none;
    transform: scale(1.05);
    opacity: 1;
}}
</style>
<div style="text-align: center; margin: 40px 0;">
    <a href="{url}" target="_blank" class="flashing-btn">
        Click here for De-KCIB Copilot
    </a>
</div>
"""

# Default static fallback
GREEN_FLASHING_LINK = get_flashing_link(full_url)

def get_conn():
    return openstack.connect(
        auth_url=os.getenv("OS_AUTH_URL"),
        application_credential_id=os.getenv("OS_APPLICATION_CREDENTIAL_ID"),
        application_credential_secret=os.getenv("OS_APPLICATION_CREDENTIAL_SECRET"),
        auth_type="v3applicationcredential",
        region_name="IU",
        interface="public"
    )

def extract_public_ip(server):
    if not server:
        return None
    if getattr(server, 'accessIPv4', None):
        return server.accessIPv4
    addresses = getattr(server, 'addresses', {}) or {}
    if not isinstance(addresses, dict):
        return None
    # Look for a floating IPv4 address that is not a private IP (e.g. 10.x.x.x)
    for net_name, addr_list in addresses.items():
        if not isinstance(addr_list, list):
            continue
        for addr in addr_list:
            if not isinstance(addr, dict):
                continue
            ip = addr.get('addr')
            if ip and addr.get('version') == 4:
                if not ip.startswith('10.'):
                    return ip
    # Fallback to any IPv4 address
    for net_name, addr_list in addresses.items():
        if not isinstance(addr_list, list):
            continue
        for addr in addr_list:
            if not isinstance(addr, dict):
                continue
            ip = addr.get('addr')
            if ip and addr.get('version') == 4:
                return ip
    return None

def get_current_status():
    global active_user_count, is_dekcib_alive
    try:
        conn = get_conn()
        instance_id = os.getenv("OS_INSTANCE_ID")
        server = conn.compute.find_server(instance_id)
        
        status_text = "❌ Error: Instance Not Found"
        ip_address = None
        if server:
            status_map = {
                "ACTIVE": "🟢 RUNNING (ACTIVE)",
                "SHELVED_OFFLOADED": "💤 SLEEPING (SHELVED)",
                "SHUTOFF": "🔴 POWERED OFF",
                "BUILD": "🛠️ STARTING...",
                "SHELVING": "⏳ SAVING STATE..."
            }
            status_text = status_map.get(server.status, f"❓ STATE: {server.status}")
            ip_address = extract_public_ip(server)
        
        target_url = full_url
        if "RUNNING" in status_text:
            if ip_address:
                # Probing both HTTP port 80 (via Nginx proxy) and direct Node port 3000
                check_urls = [f"http://{ip_address}", f"http://{ip_address}:3000"]
                is_dekcib_alive = False
                for check_url in check_urls:
                    try:
                        if requests.get(check_url, timeout=1).status_code < 500:
                            is_dekcib_alive = True
                            target_url = check_url
                            break
                    except:
                        pass
            else:
                try:
                    if requests.get(full_url, timeout=1).status_code < 500:
                        is_dekcib_alive = True
                    else:
                        is_dekcib_alive = False
                except:
                    is_dekcib_alive = False
        else:
            is_dekcib_alive = False

        link_update = gr.update(value=get_flashing_link(full_url) if is_dekcib_alive else "", visible=is_dekcib_alive)
        return status_text, f"👥 Space Visitors: {active_user_count}", link_update
    except Exception as e:
        return f"❌ Connection Error: {str(e)}", f"👥 Space Visitors: {active_user_count}", gr.update()

def user_joined():
    global active_user_count
    active_user_count += 1
    return f"👥 Space Visitors: {active_user_count}"

def user_left():
    global active_user_count
    active_user_count = max(0, active_user_count - 1)

def manage_instance():
    global is_dekcib_alive
    try:
        conn = get_conn()
        instance_id = os.getenv("OS_INSTANCE_ID")
        server = conn.compute.find_server(instance_id)
        
        if not server:
            yield ("❌ Error: Instance ID not found in Jetstream2", gr.update(visible=False))
            return

        if server.status != "ACTIVE":
            yield ("⏳ Milestone 1/3: Un-shelving De-KCIB...", gr.update(visible=False))
            if server.status == "SHELVED_OFFLOADED":
                conn.compute.unshelve_server(server)
            
            conn.compute.wait_for_server(server, status='ACTIVE', wait=600)
            yield ("✅ Milestone 2/3: VM is ACTIVE. Starting software...", gr.update(visible=False))

        # Refetch server details to extract the dynamic public IP
        server = conn.compute.find_server(instance_id)
        ip_address = extract_public_ip(server)

        yield ("🔄 Milestone 3/3: Connecting to De-KCIB Frontend...", gr.update(visible=False))
        
        check_urls = []
        if ip_address:
            check_urls.extend([f"http://{ip_address}", f"http://{ip_address}:3000"])
        check_urls.append(full_url)
        
        for i in range(30): 
            for check_url in check_urls:
                try:
                    if requests.get(check_url, timeout=1).status_code < 500:
                        is_dekcib_alive = True
                        yield ("🎉 Success! De-KCIB is ready for use.", gr.update(value=get_flashing_link(full_url), visible=True))
                        return
                except:
                    pass
            yield (f"🔄 Milestone 3/3: Software booting ({i+1}/30)...", gr.update(visible=False))
            time.sleep(5)
            
    except Exception as e:
        yield (f"❌ Error during activation: {str(e)}", gr.update(visible=False))

combined_js = """
<script>
let idleTime = 0;
const MAX_IDLE = 10;
function playNotification(status) {
    if (status.includes("RUNNING")) {
        var audio = new Audio('https://cdn.freesound.org');
        audio.play().catch(e => console.log("Audio blocked."));
    }
}
function resetTimer() { idleTime = 0; }
window.onmousemove = resetTimer; window.onmousedown = resetTimer; window.onclick = resetTimer; window.onkeypress = resetTimer;
setInterval(function() {
    idleTime++;
    if (idleTime >= MAX_IDLE) {
        alert("Space session expired due to inactivity. Reloading...");
        window.location.reload();
    }
}, 60000); 
</script>
"""

with gr.Blocks(title="De-KCIB Access Portal") as demo:
    gr.HTML(combined_js)
    session_tracker = gr.State(value="active", delete_callback=user_left)

    gr.HTML("<h1 style='font-size: 42px; text-align: center;'>De-KCIB (Deep Knowledge Center for Injury Biomechanics)</h1>")
    gr.HTML("<h3 style='font-size: 24px; text-align: center;'>Biomechanics Knowledge-based Conversational Agent by Innovision</h3>")
    
    with gr.Row():
        live_status = gr.Textbox(label="Jetstream2 Instance Status", interactive=False)
        user_display = gr.Textbox(label="Active Space Visitors", interactive=False)

    with gr.Row():
        activate_btn = gr.Button("🚀 Activate / Wake Up De-KCIB", variant="primary")
        refresh_btn = gr.Button("🔄 Refresh Status", variant="secondary")
    
    status_label = gr.Label(value="Ready")
    link_box = gr.HTML(visible=False)

    gr.Markdown("---")
    gr.Markdown("<center><h3>📖 Instructions</h3></center>")
    gr.Markdown("""
    **Access or Wake Up**  
    - If a flashing **Green Button** is already visible (above these instructions), simply click it to open De-KCIB Copilot.
    - If no flashing green button is visible, click **Activate / Wake Up De-KCIB** button (top left). This will trigger the un-shelving process, which may take up to 2+ mins.
    
    **Note A: Track Milestones**  
    When you click on wake-up, the control panel will cycle through three milestones: Un-shelving, VM Activation, and Software Booting. Please wait(1-2 mins) while the cloud prepares your environment.
    
    **Note B: Automatic Session Timeout**  
    If you do not interact with this page(or next page - De-KCIB Copilot interface) for **10 minutes**, your session will expire. 
    
    **Note C: What to do after clicking on flashing green button**  
    Once you sign-up using your email on De-KCIB Copilot page (next page), a button will pop-up showing that you need to confirm email. You can safely ignore this step(no need to open your inbox) and continue with login using information you just used for sign-up. Gmail/Microsoft 3rd party sign-up may not work for some users.
    """)

    gr.Markdown("---")
    # Updated footer with LinkedIn hyperlink for Dr. Bentley
    gr.HTML("<center><h4>Supporters & Collaborators: (Special thanks to <a href='https://www.linkedin.com/in/timothy-bentley-34423032/' target='_blank'>Dr. Timothy Bentley</a>)</h4></center>")
    with gr.Row():
        gr.Image("logo1.png", show_label=False, interactive=False, container=False, scale=1)
        gr.Image("logo2.png", show_label=False, interactive=False, container=False, scale=1)
        gr.Image("logo3.png", show_label=False, interactive=False, container=False, scale=1)

    # Logic
    demo.load(fn=user_joined, outputs=user_display)
    demo.load(fn=get_current_status, outputs=[live_status, user_display, link_box])
    
    status_timer = gr.Timer(5)
    status_timer.tick(fn=get_current_status, outputs=[live_status, user_display, link_box])
    
    live_status.change(None, inputs=live_status, js="(s) => playNotification(s)")
    activate_btn.click(fn=manage_instance, outputs=[status_label, link_box])
    refresh_btn.click(fn=get_current_status, outputs=[live_status, user_display, link_box])

demo.queue().launch()
