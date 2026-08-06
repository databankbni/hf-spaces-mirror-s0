export interface PageHelp {
    title: string;
    description: string;
    features: string[];
}

export const HELP_CONFIG: Record<string, PageHelp> = {
    '/': {
        title: 'Dashboard (Genel Bakış)',
        description: 'Uygulamanın genel sağlık durumunu ve büyüme metriklerini izleyin.',
        features: [
            'Total Users: Toplam kayıtlı kullanıcı sayısı.',
            'MAU/DAU: Aylık ve günlük aktif kullanıcı oranları.',
            'Premium Dönüşüm: Ücretli aboneliklerin genele oranı.',
            'RFM Analizi: Kullanıcı sadakati segmentasyonu.'
        ]
    },
    '/users': {
        title: 'User Management (Kullanıcı Yönetimi)',
        description: 'Kullanıcı topluluğunu yönetin ve her birinin detaylı finansal profilini analiz edin.',
        features: [
            'Arama: E-posta veya ID ile hızlı bulma.',
            'Filtreleme: Premium durumuna veya online durumuna göre filtreleme.',
            'Analyze: Kullanıcının portfolyo, watchlist ve işlem geçmişini derinlemesine inceleme.',
            'Limit Yönetimi: Kullanıcıya özel kullanım limitlerini görme.'
        ]
    },
    '/live': {
        title: 'Live Intelligence (Canlı Veri Akışı)',
        description: 'Veritabanı üzerinde gerçekleşen tüm işlemleri anlık (real-time) olarak izleyin.',
        features: [
            'Database Stream: Kayıt ekleme, silme ve güncelleme işlemlerini WebSocket üzerinden anlık görürsünüz.',
            'Active Users: Son 5 dakika içinde işlem yapan aktif kullanıcı sayısını takip eder.',
            'Incident Tracking: Kritik veritabanı değişikliklerini (örneğin DELETE) kırmızı ile vurgular.'
        ]
    },
    '/analytics': {
        title: 'Analytics Insights',
        description: 'Derinlemesine veri analizi ve churn (kayıp) tahminleri.',
        features: [
            'Veri Senkronizasyonu: Gerçek kullanıcı verilerine dayalı portfolyo dağılımları.',
            'Growth Metrics: Dönemsel büyüme grafiklerini inceleyin.'
        ]
    },
    '/system/audit-logs': {
        title: 'Audit Logs (Denetim Kayıtları)',
        description: 'Sistemdeki tüm tarihsel eylemlerin kalıcı kayıt listesi.',
        features: [
            'History: Kimin, ne zaman, hangi IP üzerinden ne yaptığını görürsünüz.',
            'Details: İşlem detayları (JSON formatında) taranabilir.',
            'Security: IP adresi ve eylem türü bazlı güvenlik takibi yapar.'
        ]
    },
    '/kvkk': {
        title: 'KVKK / GDPR Requests',
        description: 'Kullanıcıların veri silme ve hesap kapatma taleplerini yönetin.',
        features: [
            'Deletion Requests: Gelen silme taleplerini onaylayın veya takip edin.',
            'Compliance: KVKK uyumluluğu için yasal süreçleri buradan yönetin.'
        ]
    },
    '/intelligence/profile': {
        title: 'User Profile Intelligence',
        description: 'Seçilen kullanıcının finansal dünyasına derin dalış yapın.',
        features: [
            'Portfolio: Kullanıcının tüm varlıkları ve maliyetleri.',
            'Watchlist: Takip listesindeki semboller.',
            'Transactions: Gelir-gider ve banka işlemi geçmişi.'
        ]
    },
    '/strategic': {
        title: 'Strategic Decision Panel',
        description: 'Uygulamanın stratejik büyüme ve risk metriklerini analiz ederek karar almanıza yardımcı olur.',
        features: [
            'Cohort Analysis: Kullanıcıların haftalık tutunma (retention) oranları.',
            'Feature Heatmap: En popüler özelliklerin kullanım dağılımı.',
            'User Segmentation: Power User ve At-Risk kullanıcı ayrımı.',
            'Anomaly Detection: Şüpheli IP veya bot benzeri aktivitelerin tespiti.'
        ]
    }
};
