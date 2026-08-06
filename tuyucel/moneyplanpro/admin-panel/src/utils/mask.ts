/**
 * Utility functions for masking sensitive data in the admin panel.
 */

/**
 * Masks an email address: t***@e***.com
 */
export const maskEmail = (email: string | null | undefined): string => {
    if (!email) return 'N/A';
    const [local, domain] = email.split('@');
    if (!domain) return email;

    const maskedLocal = local.length > 2
        ? `${local.substring(0, 1)}*** ${local.substring(local.length - 1)} `
        : `${local.substring(0, 1)}*** `;

    const domainParts = domain.split('.');
    const maskedDomain = domainParts[0].length > 2
        ? `${domainParts[0].substring(0, 1)}*** `
        : domainParts[0];

    return `${maskedLocal} @${maskedDomain}.${domainParts.slice(1).join('.')} `;
};

/**
 * Masks a name: T*** Y***
 */
export const maskName = (name: string | null | undefined): string => {
    if (!name) return 'Anonymous';
    return name.split(' ').map(part => {
        if (part.length <= 1) return part;
        return `${part.substring(0, 1)}*** `;
    }).join(' ');
};

/**
 * Masks an ID: 5***-***1
 */
export const maskId = (id: string | null | undefined): string => {
    if (!id) return 'N/A';
    if (id.length < 8) return id;
    return `${id.substring(0, 4)}...${id.substring(id.length - 4)} `;
};

/**
 * Masks an IP address: 192.168.***.***
 */
export const maskIp = (ip: string | null | undefined): string => {
    if (!ip) return 'N/A';
    const parts = ip.split('.');
    if (parts.length !== 4) return ip;
    return `${parts[0]}.${parts[1]}.***.*** `;
};

/**
 * Masks sensitive fields in a JSON object
 */
export const maskJson = (data: any): any => {
    if (!data || typeof data !== 'object') return data;

    const sensitiveKeys = ['email', 'ip', 'ip_address', 'phone', 'password', 'token', 'secret', 'user_id', 'record_id'];
    const result = { ...data };

    for (const key in result) {
        if (sensitiveKeys.includes(key.toLowerCase())) {
            if (typeof result[key] === 'string') {
                if (key.toLowerCase().includes('email')) result[key] = maskEmail(result[key]);
                else if (key.toLowerCase().includes('ip')) result[key] = maskIp(result[key]);
                else result[key] = maskId(result[key]);
            }
        } else if (typeof result[key] === 'object') {
            result[key] = maskJson(result[key]);
        }
    }

    return result;
};
