/**
 * Utility functions for exporting data to CSV and JSON
 */

export const exportToCSV = <T extends Record<string, unknown>>(
    data: T[],
    filename: string
): void => {
    if (!data || data.length === 0) {
        console.warn('No data to export');
        return;
    }

    // Get headers from first object
    const headers = Object.keys(data[0]);

    // Create CSV content
    const csvContent = [
        // Header row
        headers.join(','),
        // Data rows
        ...data.map(row =>
            headers
                .map(header => {
                    const value = row[header];

                    // Handle different value types
                    let stringValue: string;
                    if (value === null || value === undefined) {
                        stringValue = '';
                    } else if (typeof value === 'string') {
                        stringValue = value;
                    } else if (typeof value === 'number' || typeof value === 'boolean') {
                        stringValue = value.toString();
                    } else {
                        // Fallback for objects, arrays, etc.
                        stringValue = JSON.stringify(value);
                    }
                    if (stringValue.includes(',') || stringValue.includes('"')) {
                        return `"${stringValue.replaceAll('"', '""')}"`;
                    }

                    return stringValue;
                })
                .join(',')
        ),
    ].join('\n');

    // Create and download file
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);

    link.setAttribute('href', url);
    link.setAttribute('download', `${filename}.csv`);
    link.style.visibility = 'hidden';

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
};

export const exportToJSON = <T>(data: T[], filename: string): void => {
    if (!data || data.length === 0) {
        console.warn('No data to export');
        return;
    }

    const jsonContent = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonContent], { type: 'application/json' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);

    link.setAttribute('href', url);
    link.setAttribute('download', `${filename}.json`);
    link.style.visibility = 'hidden';

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
};

export const formatDateForFilename = (): string => {
    const now = new Date();
    return now.toISOString().split('T')[0]; // YYYY-MM-DD
};
