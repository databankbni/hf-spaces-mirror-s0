from database import get_db_connection

class AdService:
    def get_all_placements(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ad_placements")
        rows = cursor.fetchall()
        placements = [dict(row) for row in rows]
        conn.close()
        return placements

    def update_placement(self, placement_id, updates):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        allowed_fields = ["name", "ad_unit_id", "is_enabled", "provider"]
        update_parts = []
        params = []
        
        for field in allowed_fields:
            if field in updates:
                update_parts.append(f"{field} = ?")
                params.append(updates[field])
        
        if not update_parts:
            conn.close()
            return False, "No valid fields to update"
            
        params.append(placement_id)
        cursor.execute(f"UPDATE ad_placements SET {', '.join(update_parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success, "Updated" if success else "Placement not found"

    def get_active_ads_for_app(self):
        """Minimal endpoint for mobile app consumption"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT placement_key, provider, ad_unit_id, is_enabled FROM ad_placements")
        rows = cursor.fetchall()
        ads = {row["placement_key"]: dict(row) for row in rows}
        conn.close()
        return ads

ad_service = AdService()
