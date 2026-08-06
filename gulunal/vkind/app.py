import gradio as gr
import os

# Zengin içerikli film veritabanı (8 Farklı Tür, Toplam 48 Film)
movies_db = {
    "Aksiyon": [
        {"title": "Mad Max: Fury Road", "year": 2015, "director": "George Miller", "rating": "8.1/10", "desc": "Zorba bir hükümdardan kaçan bir grup kadının, çöllerle kaplı dünyada başlattığı destansı kaçış hikayesi."},
        {"title": "The Dark Knight", "year": 2008, "director": "Christopher Nolan", "rating": "9.0/10", "desc": "Batman, Gotham'ı kaosa sürüklemeye çalışan psikopat ruhlu Joker ile tarihin en tehlikeli mücadelesine girer."},
        {"title": "John Wick", "year": 2014, "director": "Chad Stahelski", "rating": "7.4/10", "desc": "Emekli olmuş efsanevi bir tetikçinin, her şeyini elinden alan adamlara karşı başlattığı durdurulamaz intikam savaşı."},
        {"title": "Gladiator", "year": 2000, "director": "Ridley Scott", "rating": "8.5/10", "desc": "Romalı bir generalin, ailesini katleden ve kendisini köleliğe mahkum eden imparatordan intikam alma mücadelesi."},
        {"title": "Top Gun: Maverick", "year": 2022, "director": "Joseph Kosinski", "rating": "8.3/10", "desc": "Otuz yılı aşkın hizmetten sonra, donanmanın en iyi pilotlarından Maverick'in genç pilotları özel bir göreve hazırlama hikayesi."},
        {"title": "Inception", "year": 2010, "director": "Christopher Nolan", "rating": "8.8/10", "desc": "İnsanların zihinlerine rüya anında sızarak en gizli sırları çalan profesyonel bir hırsızın son ve en zorlu görevi."}
    ],
    "Bilim Kurgu": [
        {"title": "Interstellar", "year": 2014, "director": "Christopher Nolan", "rating": "8.7/10", "desc": "Dünyanın sonu yaklaşırken, insanlık için yeni bir yaşanabilir gezegen arayan bir grup astronotun zaman ve uzay büken yolculuğu."},
        {"title": "The Matrix", "year": 1999, "director": "Lana Wachowski, Lilly Wachowski", "rating": "8.7/10", "desc": "Sıradan bir yazılımcının, tüm insanlığın aslında makineler tarafından kontrol edilen bir simülasyonun içinde yaşadığını keşfetmesi."},
        {"title": "Blade Runner 2049", "year": 2017, "director": "Denis Villeneuve", "rating": "8.0/10", "desc": "Yeni bir replikantın, toplumdan geri kalanını kaosa sürükleyecek uzun süredir gizlenmiş bir sırrı açığa çıkarması."},
        {"title": "Dune: Part Two", "year": 2024, "director": "Denis Villeneuve", "rating": "8.6/10", "desc": "Paul Atreides'in, ailesini yok eden komploculara karşı Fremen halkıyla birleşerek başlattığı görkemli intikam savaşı."},
        {"title": "Arrival", "year": 2016, "director": "Denis Villeneuve", "rating": "7.9/10", "desc": "Dünyaya iniş yapan gizemli uzay araçlarıyla iletişim kurması için işe alınan bir dilbilimcinin, insanlığın geleceğini belirleyecek keşfi."},
        {"title": "The Prestige", "year": 2006, "director": "Christopher Nolan", "rating": "8.5/10", "desc": "19. yüzyıl Londra'sında, birbirini alt etmeye çalışan iki rakip sihirbazın takıntı, hırs ve fedakarlık dolu dramatik savaşı."}
    ],
    "Komedi": [
        {"title": "The Hangover", "year": 2009, "director": "Todd Phillips", "rating": "7.7/10", "desc": "Bekarlığa veda partisi sonrası Las Vegas'ta uyanan ve kayıp damadı bulmaya çalışan üç arkadaşın çılgın macerası."},
        {"title": "Ölümlü Dünya", "year": 2018, "director": "Ali Atay", "rating": "7.6/10", "desc": "Nesillerdir uluslararası bir suç örgütü için tetikçilik yapan Mermer ailesinin, kimliklerinin deşifre olmasıyla yaşadığı absürt komedi."},
        {"title": "Superbad", "year": 2007, "director": "Greg Mottola", "rating": "7.6/10", "desc": "Lise son sınıf öğrencisi iki arkadaşın, mezun olmadan önce popüler olma ve kızları etkileme çabaları üzerine eğlenceli hikayesi."},
        {"title": "G.O.R.A.", "year": 2004, "director": "Ömer Faruk Sorak", "rating": "8.0/10", "desc": "Kurnaz bir halı tüccarı olan Arif'in uzaylılar tarafından kaçırılması ve esir tutulduğu gezegenden kaçma çabaları."},
        {"title": "The Grand Budapest Hotel", "year": 2014, "director": "Wes Anderson", "rating": "8.1/10", "desc": "Ünlü bir Avrupa otelinin kapıcısı ile komiğinin, paha biçilemez bir Rönesans tablosunun çalınması etrafında dönen maceraları."},
        {"title": "The Truman Show", "year": 1998, "director": "Peter Weir", "rating": "8.1/10", "desc": "Tüm hayatının aslında devasa bir stüdyoda, 24 saat canlı yayınlanan bir televizyon şovundan ibaret olduğunu keşfeden adamın trajikomik hikayesi."}
    ],
    "Dram": [
        {"title": "The Shawshank Redemption", "year": 1994, "director": "Frank Darabont", "rating": "9.3/10", "desc": "İşlemediği bir cinayet yüzünden hapse giren bankacı Andy Dufresne'in, umudunu hiç kaybetmeden hapishanede kurduğu dostluklar ve özgürlük mücadelesi."},
        {"title": "Forrest Gump", "year": 1994, "director": "Robert Zemeckis", "rating": "8.8/10", "desc": "Öğrenme güçlüğü olan saf bir adamın, hayatı boyunca istemeden de olsa 20. yüzyılın en önemli tarihi anlarına tanıklık etmesi ve büyük aşkı."},
        {"title": "Whiplash", "year": 2014, "director": "Damien Chazelle", "rating": "8.5/10", "desc": "Geleceğin en iyi caz davulcularından biri olmak isteyen genç bir konservatuar öğrencisinin, acımasız hocasıyla olan yıpratıcı mücadelesi."},
        {"title": "The Green Mile", "year": 1999, "director": "Frank Darabont", "rating": "8.6/10", "desc": "Bir hapishanede infaz koruma memuru olan Paul'ün, doğaüstü iyileştirme güçlerine sahip devasa ama çocuk ruhlu bir mahkumla tanışması."},
        {"title": "Parasite", "year": 2019, "director": "Bong Joon Ho", "rating": "8.5/10", "desc": "Yoksul bir ailenin fertlerinin, kendilerini zengin bir ailenin hizmetçileri olarak konumlandırmak için kurdukları tehlikeli planlar zinciri."},
        {"title": "The Pianist", "year": 2002, "director": "Roman Polanski", "rating": "8.5/10", "desc": "İkinci Dünya Savaşı sırasında Nazi işgali altındaki Polonya'da hayatta kalmaya çalışan dahi bir Yahudi piyanistin gerçek yaşam öyküsü."}
    ],
    "Korku & Gerilim": [
        {"title": "The Shining", "year": 1980, "director": "Stanley Kubrick", "rating": "8.4/10", "desc": "Kış sezonunda kapalı olan devasa bir otelin bakımını üstlenen bir yazarın ve ailesinin, oteldeki doğaüstü güçlerle deliliğe sürüklenmesi."},
        {"title": "Get Out", "year": 2017, "director": "Jordan Peele", "rating": "7.8/10", "desc": "Sevgilisinin ailesinin malikanesine giden siyahi bir gencin, ailenin arkasındaki korkunç ve gizemli gerçeği fark etmesiyle başlayan gerilim."},
        {"title": "A Quiet Place", "year": 2018, "director": "John Krasinski", "rating": "7.5/10", "desc": "Sese duyarlı gizemli yaratıkların avlandığı bir dünyada, hayatta kalabilmek için tamamen sessiz yaşamak zorunda olan bir ailenin hikayesi."},
        {"title": "Seven", "year": 1995, "director": "David Fincher", "rating": "8.6/10", "desc": "İncil'de geçen yedi ölümcül günahı temel alarak cinayetler işleyen bir seri katilin peşine düşen iki dedektifin sürükleyici macerası."},
        {"title": "Shutter Island", "year": 2010, "director": "Martin Scorsese", "rating": "8.2/10", "desc": "Bir akıl hastasının kayboluşunu araştırmak üzere adadaki psikiyatri hastanesine giden iki dedektifin zihin bulandıran hikayesi."},
        {"title": "Psycho", "year": 1960, "director": "Alfred Hitchcock", "rating": "8.5/10", "desc": "Yolunu kaybeden bir kadının, garip bir genç adam tarafından işletilen ücra bir motelde konaklamasıyla başlayan sinema tarihinin en ünlü gerilimi."}
    ],
    "Animasyon": [
        {"title": "Spirited Away", "year": 2001, "director": "Hayao Miyazaki", "rating": "8.6/10", "desc": "Ailesi gizemli bir kasabada domuza dönüşen küçük Chihiro'nun, onları kurtarmak için ruhlar dünyasındaki bir hamamda çalışmaya başlaması."},
        {"title": "Spider-Man: Into the Spider-Verse", "year": 2018, "director": "Bob Persichetti", "rating": "8.4/10", "desc": "Farklı boyutlardan gelen Örümcek-Adamların, dünyayı yok etmek isteyen bir tehlikeye karşı Miles Morales önderliğinde birleşmesi."},
        {"title": "Coco", "year": 2017, "director": "Lee Unkrich", "rating": "8.4/10", "desc": "Müzisyen olma hayali kuran küçük Miguel'in, yanlışlıkla kendisini atalarının bulunduğu Ölüler Diyarı'nda bulmasıyla başlayan rengarenk yolculuk."},
        {"title": "WALL·E", "year": 2008, "director": "Andrew Stanton", "rating": "8.4/10", "desc": "Gelecekte, insanlar tarafından terk edilmiş çöp yığını halindeki dünyada yalnız kalan küçük bir temizlik robotunun uzaydaki aşk ve macera dolu serüveni."},
        {"title": "The Lion King", "year": 1994, "director": "Roger Allers", "rating": "8.5/10", "desc": "Babası öldürülen yavru aslan Simba'nın, tahtını amcasından geri almak için çıktığı olgunlaşma ve liderlik yolculuğu."},
        {"title": "Inside Out", "year": 2015, "director": "Pete Docter", "rating": "8.1/10", "desc": "Yeni bir şehre taşınan küçük Riley'nin beynindeki Neşe, Üzüntü, Öfke, Korku ve Tiksinme duygularının hayatı kontrol etme çabası."}
    ],
    "Gizem & Dedektiflik": [
        {"title": "Knives Out", "year": 2019, "director": "Rian Johnson", "rating": "7.9/10", "desc": "Ünlü bir suç yazarının ölümünü araştırmak üzere görevlendirilen eksantrik dedektif Benoit Blanc'ın, şüpheli aile üyelerini sorgulama süreci."},
        {"title": "Sherlock Holmes", "year": 2009, "director": "Guy Ritchie", "rating": "7.6/10", "desc": "Efsanevi dedektif Sherlock Holmes ve ortağı Dr. Watson'ın, tüm ülkeyi tehdit eden karanlık bir tarikat liderini durdurma mücadelesi."},
        {"title": "The Girl with the Dragon Tattoo", "year": 2011, "director": "David Fincher", "rating": "7.8/10", "desc": "Bir gazeteci ile asi bir hacker kızın, kırk yıl önce ortadan kaybolan bir kadının gizemini çözmek için bir araya gelmesi."},
        {"title": "Memento", "year": 2000, "director": "Christopher Nolan", "rating": "8.4/10", "desc": "Kısa süreli hafıza kaybı yaşayan bir adamın, karısının katilini bulmak için vücuduna dövmeler yaparak ve fotoğraflar çekerek ipuçlarını izlemesi."},
        {"title": "Zodiac", "year": 2007, "director": "David Fincher", "rating": "7.7/10", "desc": "San Francisco'da yıllarca panik yaratan ve arkasında şifreli mektuplar bırakan gizemli bir seri katilin peşine düşen karikatürist ve dedektiflerin hikayesi."},
        {"title": "Prisoners", "year": 2013, "director": "Denis Villeneuve", "rating": "8.2/10", "desc": "Küçük kızı kaçırılan acılı bir babanın, adaletin yavaş kalması üzerine şüpheliyi bizzat sorgulamaya karar vermesiyle gelişen sarsıcı gerilim."}
    ],
    "Romantik": [
        {"title": "La La Land", "year": 2016, "director": "Damien Chazelle", "rating": "8.0/10", "desc": "Los Angeles'ta yolları kesişen hayalperest bir oyuncu adayı ile caz piyanistinin aşk ve kariyer arasındaki sancılı mücadelesi."},
        {"title": "About Time", "year": 2013, "director": "Richard Curtis", "rating": "7.8/10", "desc": "Ailesindeki erkeklerin zamanda yolculuk yapabildiğini öğrenen genç bir adamın, bu yeteneğini mükemmel bir aşk hayatı kurmak için kullanması."},
        {"title": "Eternal Sunshine of the Spotless Mind", "year": 2004, "director": "Michel Gondry", "rating": "8.3/10", "desc": "İlişkileri kötü giden bir çiftin, birbirleriyle ilgili anılarını tıbbi bir operasyonla sildirmesiyle başlayan düşsel ve duygusal yolculuk."},
        {"title": "Pride & Prejudice", "year": 2005, "director": "Joe Wright", "rating": "7.8/10", "desc": "19. yüzyıl İngiltere'sinde, beş kız kardeşten biri olan Elizabeth Bennet ile zengin ancak gururlu Bay Darcy arasındaki zorlu ama tutkulu aşk."},
        {"title": "Before Sunrise", "year": 1995, "director": "Richard Linklater", "rating": "8.1/10", "desc": "Viyana'da bir trende tanışan Amerikalı bir genç ile Fransız bir kadının, şehirde geçirdikleri tek bir büyülü ve sohbet dolu gecenin hikayesi."},
        {"title": "Amélie", "year": 2001, "director": "Jean-Pierre Jeunet", "rating": "8.3/10", "desc": "Paris'te yaşayan saf ve hayalperest bir garson kızın, çevresindeki insanların hayatını gizlice güzelleştirirken kendi aşkını da bulması."}
    ]
}

def recommend_movies(genre):
    """
    Seçilen türe ait filmleri filtreler ve şık HTML kartlar halinde döndürür.
    """
    movies = movies_db.get(genre, [])
    if not movies:
        return "<div style='text-align: center; color: #e53e3e; padding: 20px; font-weight: bold;'>Aradığınız türde henüz öneri bulunamadı.</div>"
    
    html_content = "<div style='display: flex; flex-direction: column; gap: 20px; width: 100%;'>"
    for movie in movies:
        html_content += f"""
        <div style="background: linear-gradient(135deg, #ffffff 0%, #f7fafc 100%); 
                    border: 1px solid #e2e8f0; 
                    border-radius: 12px; 
                    padding: 20px; 
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                    transition: transform 0.2s ease-in-out;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <h3 style="margin: 0; font-size: 20px; color: #1a202c; font-weight: 700;">🎬 {movie['title']}</h3>
                <span style="background-color: #ecc94b; color: #744210; font-weight: bold; padding: 4px 8px; border-radius: 6px; font-size: 13px;">⭐ {movie['rating']}</span>
            </div>
            <div style="font-size: 14px; color: #718096; margin-bottom: 12px;">
                <strong>Yıl:</strong> {movie['year']} &nbsp;|&nbsp; <strong>Yönetmen:</strong> {movie['director']}
            </div>
            <p style="margin: 0; font-size: 15px; color: #4a5568; line-height: 1.5;">{movie['desc']}</p>
        </div>
        """
    html_content += "</div>"
    return html_content

# Gradio uygulamasını Soft temasıyla oluşturuyoruz
with gr.Blocks(theme=gr.themes.Soft(primary_hue="rose", secondary_hue="slate")) as demo:
    
    gr.Markdown(
        """
        # 🍿 Sinematik Öneri İstasyonu
        Sizin için özenle seçilmiş film arşivimizden dilediğiniz türü seçin, anında mükemmel film tavsiyelerine ulaşın!
        """
    )
    
    with gr.Row():
        with gr.Column(scale=1):
            genre_input = gr.Dropdown(
                choices=list(movies_db.keys()),
                label="Film Türü Seçiniz",
                value="Aksiyon",
                interactive=True,
                info="İzlemek istediğiniz film tarzını buradan belirleyebilirsiniz."
            )
            submit_btn = gr.Button("🔍 Bana Film Öner", variant="primary")
            
        with gr.Column(scale=2):
            gr.Markdown("### 👇 Seçtiğiniz Türden Film Önerileri")
            # Başlangıçta doğrudan 'Aksiyon' türündeki filmleri gösteriyoruz
            output_html = gr.HTML(value=recommend_movies("Aksiyon"))

    # Butona tıklandığında tavsiyeleri yükle
    submit_btn.click(
        fn=recommend_movies,
        inputs=genre_input,
        outputs=output_html
    )
    
    # Kullanıcı açılır menüyü değiştirdiğinde otomatik güncelleme yapması için:
    genre_input.change(
        fn=recommend_movies,
        inputs=genre_input,
        outputs=output_html
    )

if __name__ == "__main__":
    # Hugging Face üzerinde çökme ve kilitlenmeleri önlemek için port ve host değerlerini sabitliyoruz
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860
    )