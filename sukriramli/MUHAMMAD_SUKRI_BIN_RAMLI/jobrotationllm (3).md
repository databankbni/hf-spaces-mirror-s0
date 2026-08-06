# jobrotationllm (3)

[Link to original PDF](jobrotationllm (3).pdf)

---

ENHANCING JOB ROTATION ONBOARDING IN THE MALAYSIAN PUBLIC 
SECTOR: A NotebookLM Large Language Model Case Study 
MUHAMMAD SUKRI BIN RAMLI 
Asia School of Business 
Kuala Lumpur, Malaysia 
Email: m.binramli@sloan.mit.edu 
Abstract 
Mandatory job rotations are a cornerstone of the Malaysian civil service, designed to enhance governance, reduce 
integrity risks, and foster organizational agility. However, these rotations present significant onboarding challenges, requiring 
employees to rapidly adapt to diverse roles and complex responsibilities, particularly in 'hot seat' and high-risk-to-corruption 
positions. This study focuses on the Jabatan Kastam Diraja Malaysia (JKDM), where the need for efficient onboarding is 
heightened by the structured tenure of job rotations. The necessity to quickly acclimate to new roles within a defined period, 
especially in sensitive positions, underscores the urgency of effective onboarding strategies. To address the inherent 
onboarding complexities, particularly in navigating intricate customs regulations, this research proposes leveraging Large 
Language Models (LLMs), with a specific focus on NotebookLM. NotebookLM's ability to ingest and summarize extensive 
regulatory documents, coupled with features like interactive training modules and AI-powered Q&A, offers a dynamic, 
personalized learning experience. This approach aims to surpass traditional training limitations, streamlining onboarding, 
enhancing knowledge transfer, and boosting productivity within JKDM. The study outlines an implementation plan, including 
a pilot program and department-wide rollout, with expected outcomes of improved onboarding efficiency, enhanced 
knowledge sharing, and increased operational effectiveness, ultimately contributing to a more agile and integrity-driven public 
service. 
Figure 1: Causal-Loop Relationship Between Job Rotation, Knowledge Transfer and Organizational Integrity 

1. 
Introduction 
The Malaysian public sector plays a crucial role in the country's economy and governance, employing a significant 
portion of the workforce and providing essential services to citizens (Malaysian Administrative Modernization and 
Management Planning Unit, 2010). As of 2024, the public sector employed approximately 1.6 million civil servants, 
highlighting its size and importance in Malaysia's socio-economic development (Prime Minister's Office of Malaysia, 2024). 
The sector encompasses a wide range of services, including healthcare, education, infrastructure development, and social 
welfare programs, all of which are vital for the well-being of Malaysian citizens (Economic Planning Unit, 2010). 
Within this large and complex sector, job rotation is a common practice aimed at enhancing employee development, 
facilitating knowledge sharing, and enabling cross-training across different government agencies and departments (Bauer & 
Erdogan, 2011; Campion, Cheraskin, & Stevens, 1994). The Public Service Department (JPA) provides a general framework 
for job rotation, emphasizing its role in talent management and career development (Jabatan Perkhidmatan Awam, 2015). The 
frequency, duration, and selection process for job rotations vary depending on the specific agency and position, allowing for 
flexibility and customization based on organization needs and circumstances (Jabatan Perkhidmatan Awam, 2015). This 
approach to talent management is designed to foster a versatile and well-rounded workforce capable of adapting to the evolving 
needs of the public sector (Jabatan Perkhidmatan Awam, 2018). 
Despite the benefits of job rotation, civil servants often encounter challenges during the onboarding process, 
particularly when adapting to new roles, responsibilities, and organizational cultures (Bauer & Erdogan, 2011). These 
challenges can hinder their ability to quickly integrate and contribute effectively to their new positions (Noe et al., 2017). One 
major challenge is information overload, where the sheer volume of documents, regulations, and procedures to learn can be 
overwhelming, especially when transitioning to a new agency or department with its own unique set of rules and practices 
(Noe et al., 2017). This overload can lead to confusion and frustration, slowing down the onboarding process and impacting 
employee performance (Bauer & Erdogan, 2011). 
Furthermore, varied procedures across different agencies and departments pose a significant hurdle for employees 
undergoing job rotation (Noe et al., 2017). Each agency may have its own specific workflows, documentation styles, and 
approval processes, requiring employees to constantly adjust and relearn how to perform tasks (Noe et al., 2017). This 
inconsistency can lead to delays, errors, and a sense of disorientation, particularly for those new to the agency or department 
(Bauer & Erdogan, 2011). In addition to procedural variations, knowledge gaps can also present challenges during onboarding 
(Noe et al., 2017). Identifying and addressing these gaps efficiently can be difficult, especially when transitioning to a role that 
requires specialized expertise or knowledge of specific regulations and policies (Campion et al., 1994). 
The limited time available for onboarding further exacerbates these challenges. Time constraints due to the demands 
of public service delivery often mean that employees have to quickly get up to speed in their new roles (Noe et al., 2017). This 
pressure can limit the depth of training and support provided, potentially leaving employees feeling unprepared and hindering 
their ability to perform their duties effectively (Bauer & Erdogan, 2011). Finally, inconsistent onboarding experiences across 
agencies and departments can create disparities in employee preparedness and performance (Noe et al., 2017). Some agencies 
may have well-structured onboarding programs with comprehensive training and support, while others may have more ad hoc 
approaches, leading to variations in the quality and effectiveness of the onboarding process (Bauer & Erdogan, 2011). This 
inconsistency can affect employee morale, productivity, and overall job satisfaction (Noe et al., 2017). 
This research focuses specifically on the JKDM, also known as the Royal Malaysian Customs Department, as a case 
study to demonstrate the potential of NotebookLM in addressing the challenges of job rotation onboarding. JKDM is a 
particularly relevant case for several reasons. First, JKDM officers operate in a high-risk environment where corruption is a 
significant concern.  The mandatory rotation of officers, especially those in "hot seat" and sensitive positions, necessitates 
rapid and effective onboarding to ensure compliance and minimize vulnerabilities. Second, JKDM deals with a vast and 
complex body of customs regulations, requiring officers to possess a thorough understanding of various laws, tariffs, and 
procedures. This complexity can be overwhelming for officers transitioning to different roles within JKDM, especially under 
the time constraints of structured tenure. Third, JKDM has a wide range of roles and responsibilities, from enforcement and 
valuation to investigation and intelligence.  Each role demands specialized knowledge and skills, and officers undergoing job 
rotation must quickly adapt to these new demands. Finally, the trade environment is dynamic and constantly evolving, with 
frequent updates and amendments to customs regulations and international trade agreements. This necessitates continuous 
learning and adaptation for JKDM officers to stay abreast of the latest developments. The challenges faced by JKDM officers 
during job rotation onboarding are representative of the broader challenges faced by civil servants across various agencies and 
departments in the Malaysian public sector. Therefore, the successful implementation of Large Language Model within JKDM 
can serve as a model for other agencies seeking to improve their onboarding processes, enhance knowledge transfer, and 
promote integrity within their workforce. 

Figure 2:  Flowchart of Job Rotation Program in Civil Service 
2. 
Problem Statement 
The challenges faced by Malaysian civil servants during job rotation onboarding are multifaceted and deeply ingrained 
in the structure and practices of the public sector. One prominent challenge is the varied agency procedures across different 
government bodies (Noe et al., 2017). For instance, document formats, approval processes, and communication protocols can 
differ significantly between agencies, creating confusion and hindering smooth transitions for employees (Noe et al., 2017). 
This lack of standardization necessitates that employees relearn processes with each rotation, leading to inefficiencies and 
potential delays in service delivery (Bauer & Erdogan, 2011). 
Another significant issue is documentation accessibility. Currently, essential documents like regulations, circulars, and 
guidelines are often scattered across various platforms, including physical files, internal websites, and shared drives (Ismail & 
Ahmad, 2012; Yusoff & Hassan, 2010). This fragmented system makes it difficult for employees to locate the necessary 
information quickly and efficiently, especially during onboarding when they are unfamiliar with the agency's knowledge 
repositories (Awang & Ahmad, 2009). Moreover, outdated versions of documents may persist, leading to potential errors and 
inconsistencies in work processes (Davenport & Prusak, 1998). 
Traditional onboarding methods often prove ineffective in ensuring knowledge retention. Passive learning approaches, 
such as lectures or reading materials, may not fully engage employees or provide opportunities for practical application of 
knowledge (Chen et al., 2021). This can result in superficial understanding and difficulty in applying learned information to 
real-world scenarios (Hwang et al., 2020). Furthermore, limited opportunities for interaction and knowledge sharing can hinder 
the development of a deeper understanding and the ability to retain information long-term (Nonaka & Takeuchi, 1995). 
Time constraints pose a significant obstacle to effective onboarding. The demanding nature of public service delivery 
often leaves limited time for comprehensive training and knowledge transfer (Noe et al., 2017). Employees are expected to 
quickly integrate into their new roles and contribute to the agency's operations, leaving little room for in-depth learning and 
development (Bauer & Erdogan, 2011). This pressure to perform can lead to a superficial understanding of job responsibilities 
and a reliance on "learning on the job," which may not always be the most efficient or effective approach (Campion et al., 
1994). 
Standardizing best practices across different agencies is crucial for improving overall public sector performance, but 
it presents significant challenges (Andriopoulos & Lowe, 2017; Gil-Garcia & Pardo, 2017). Communication barriers, lack of 
a centralized platform for knowledge sharing, and varying levels of commitment to adopting best practices can hinder their 
dissemination and implementation (OECD, 2019). This can lead to inconsistencies in service delivery and hinder the public 
sector's ability to adapt and improve its operations (Dunleavy et al., 2006). 
Finally, the need to identify level of digital literacy among some government servants poses a challenge for 
implementing technology-driven solutions like Large Language Model. While the Malaysian government is actively 
promoting digital transformation, the level of digital literacy varies across individuals and agencies (Ting, Osman, & Ting, 
2016). This disparity can create a digital divide, where some employees may struggle to utilize the full potential of digital 
tools, hindering the effectiveness of technology-driven initiatives (Said, Alam, & Zainuddin, 2016). 

Figure 3:  Visualization of Onboarding Process with Large Language Model 
Within the broader context of the Malaysian public sector, the JKDM faces unique challenges related to job rotation 
onboarding. One of the most significant challenges is the sheer volume and complexity of customs regulations (Zakaria & 
Ahmad, 2021). JKDM officers must be well-versed in a vast array of laws, tariffs, and procedures, including the Customs Act 
1967, the Excise Act 1976, Sales Tax Act 2018, Service Tax Act 2018, and various Free Trade Agreements (FTAs). These 
regulations are often complex and subject to frequent amendments, making it challenging for officers to quickly grasp and 
apply them in their daily work (Yusoff & Hassan, 2019). For example, the classification of goods for import and export duties 
can be highly intricate, requiring officers to have a deep understanding of tariff codes and their interpretations (Rahman & 
Ahmad, 2017). 
Another challenge stems from the diverse roles within JKDM. The department comprises various units and divisions, 
each with specific responsibilities and expertise. For example, the Enforcement Division focuses on preventing smuggling and 
other customs offences, while the Valuation and Classification Division determines the value and tariff classification of goods. 
Each role requires a distinct set of knowledge and skills, making it challenging for officers to transition seamlessly between 
different areas of the department (Yusoff & Hassan, 2019). An officer moving from enforcement to valuation, for instance, 
would need to acquire new knowledge on valuation methods, customs procedures, and relevant legislation (Zakaria & Ahmad, 
2021). 
Furthermore, keeping up-to-date with changes in customs regulations and international trade poses a significant 
challenge for JKDM (Omar & Hassan, 2019). The dynamic nature of global trade means that customs procedures, tariffs, and 
agreements are constantly evolving (Al-Shboul, Abdallah, & Abdallah, 2021). JKDM officers need to be aware of these 
changes to ensure compliance and effective enforcement of regulations (Nawi & Salleh, 2021). This requires continuous 
learning and access to updated information, which can be challenging to achieve through traditional training methods and 
knowledge dissemination channels (Hussin & Said, 2020). For example, changes in FTA regulations or the introduction of 
new technologies or application for customs processes require officers to update their knowledge and skills promptly (Sidek 
& Abdullah, 2018). 
This research explores the challenges faced by Malaysian civil servants during job rotation onboarding, particularly 
the information overload and procedural variations across agencies.  The research uses the JKDM as a case study, highlighting 
the complexities of customs regulations and the diverse roles within the department.  The proposed solution is NotebookLM, 
a large language model (LLM), to create a centralized knowledge repository, interactive training modules, and AI-powered 

Q&A system.  The implementation process includes a pilot program and department-wide rollout.  Expected outcomes include 
improved onboarding efficiency, enhanced knowledge sharing, and increased productivity.     
Given that NotebookLM is a complimentary addition to the Malaysian government's Google Workspace package, the 
cost-benefit analysis should be revisited.  The acquisition cost of NotebookLM is eliminated, making implementation more 
attractive financially.  Financial objections would likely be minimized, but other sources of resistance, such as unfamiliarity 
with AI or fear of job displacement, still need to be addressed.  The implementation strategy might focus more on training, 
support, and integration with existing systems, rather than on budgeting and procurement processes.     
Successful integration of NotebookLM into the Malaysian public sector requires a nuanced understanding of its 
capabilities and the specific challenges it presents. Rather than merely acknowledging potential obstacles, the research must 
delve into the practical implications of implementing this AI-driven knowledge synthesis tool. Critically, ensuring accurate 
and ethical information processing is paramount; the research must evaluate the platform's ability to handle Bahasa Malaysia 
and diverse document types prevalent in government workflows, while mitigating the risk of AI-generated misinformation or 
biased interpretations, thus ensuring alignment with government policy and ethical guidelines. Furthermore, the research 
should explore how to facilitate seamless human-AI collaboration, focusing on training programs that empower users to 
leverage the platform's capabilities while maintaining critical thinking and contextual awareness, thereby bridging the human-
AI collaboration gap.  
Given the sensitive nature of government data, data security and confidentiality are paramount, necessitating an 
investigation into how NotebookLM handles and protects sensitive information, ensuring compliance with Malaysian data 
privacy laws and regulations. To demonstrate the value of NotebookLM, the research must develop a robust evaluation 
framework that measures its impact on efficiency and decision-making, assessing how the platform streamlines information 
processing, enhances knowledge management, and supports evidence-based policy formulation. Finally, implementation 
success depends on how well NotebookLM integrates with existing government workflows and systems; the research should 
examine the technical and organizational aspects of integration, including data interoperability, system compatibility, and user 
adoption, developing strategies to minimize disruption and ensure a smooth transition. By focusing on these specific aspects, 
the research will provide a targeted and actionable analysis of the challenges and opportunities associated with implementing 
NotebookLM in the Malaysian public sector, enabling policymakers to make informed decisions for its successful and 
responsible adoption. 
Figure 4:  Royal Malaysian Customs Knowledge Cortex Framework 

3. 
Proposed Solution 
Addressing the complexities of job rotation onboarding within the Malaysian public sector, and particularly the specific 
demands of JKDM, a technology-driven solution can offer significant improvements.  Leveraging advanced AI capabilities 
presents a promising approach to enhance how government servants acquire and utilize knowledge in new roles, aiming to 
foster a more efficient, engaging, and ultimately more effective onboarding process across the Malaysian public sector.  One 
such platform that embodies this approach is NotebookLM. 
A core onboarding hurdle remains the sheer volume of information new employees must absorb, often dispersed across 
disparate systems and formats.  Establishing a centralized knowledge repository can directly tackle this challenge.  This 
repository, as implemented in platforms like NotebookLM, digitizes and organizes crucial documents – circulars, regulations, 
guidelines, and more – potentially eliminating the need for time-consuming searches across multiple platforms.  By ensuring 
streamlined access to current document versions, such systems can contribute to improved operational efficiency and accuracy. 
This centralized digital approach can deliver several advantages:  employees may gain more rapid and effortless information 
access anytime, anywhere.  Furthermore, robust search functionality, a feature of platforms like NotebookLM, enables efficient 
location of specific details within the knowledge base, while automated change tracking can help ensure users are working 
with updated information.  Digitization may also reduce reliance on physical documents, potentially conserving valuable space 
and resources. 
Technology can also foster a culture of collaborative learning and knowledge sharing by providing tools and features 
that enable employees to connect and learn from each other.  Platforms like NotebookLM offer features such as shared 
notebooks for collaborative editing and feedback.  Collaborative knowledge sharing can offer advantages. Employees may 
learn from peer experiences and expertise, potentially creating a supportive learning environment. Organizational knowledge 
and best practices can be more readily shared, contributing to continuous improvement. Collaborative learning initiatives can 
support the development of teamwork and communication skills. 
Leveraging AI capabilities, technology solutions can establish Q&A systems, offering on-demand support and 
guidance throughout the onboarding journey. Such intelligent systems, as demonstrable in platforms like NotebookLM, may 
interpret natural language questions and deliver relevant answers to frequently asked queries. This type of AI-powered Q&A 
system can yield several potential benefits: employees may receive faster answers, potentially reducing delays in seeking 
assistance. By providing readily available support, the system could free up senior officers to focus on other responsibilities.  
Furthermore, streamlined information access may contribute to a more efficient onboarding process, enhancing overall 
efficiency. 
Understanding that digital literacy levels may vary across the government workforce, technology can be utilized to 
deliver targeted digital literacy training. This training, potentially facilitated by platforms like NotebookLM, can include 
tutorials on basic computer skills, guides on utilizing relevant digital tools, and assessments to evaluate digital proficiency. By 
providing this focused training, technology can contribute to bridging the digital divide. This may help ensure that employees 
possess the necessary digital skills for effective platform and digital tool utilization.  Focused training may support digital 
inclusion, fostering a more equitable workplace where every employee can actively participate and contribute, irrespective of 
their digital literacy level. Moreover, it could build digital confidence, encouraging employees to embrace and effectively 
leverage technology in their daily work. 
To promote inclusivity and broad accessibility, technology solutions can incorporate multilingual support.  Offering a 
Bahasa Melayu interface, as seen in platforms like NotebookLM, is one example. This vital multilingual feature can allow 
employees to engage with the platform in their preferred language, potentially enhancing comfort and comprehension. 
Crucially, multilingual approaches can support inclusivity, enabling personnel, regardless of linguistic preference, to more 
easily access and benefit from the platform. A Bahasa Melayu interface may increase accessibility for employees less proficient 
in English and reflect a commitment to respecting the diverse linguistic landscape of the Malaysian public sector. 
To address JKDM's specific operational needs, technology solutions can be designed for integration with the 
department’s existing digital infrastructure. Integration with iPatuh, JKDM’s internal platform, serves as a prime example. By 
connecting iPatuh and a platform like NotebookLM via integration method for example API integration, data connectors, 
JKDM officers could gain unified access to critical information within a single interface. This streamlined access to vital 
resources may help ensure officers more consistently work with current regulations and procedures, potentially enhancing 
efficiency and mitigating risks associated with outdated information and potential errors. This centralized knowledge 
repository could contribute to greater consistency in decision-making, potentially equipping officers to more effectively 
navigate customs operations. 
This comprehensive approach to technology implementation within JKDM suggests its potential to address 
department-specific challenges and enhance workforce capabilities.  By offering tailored features and leveraging AI, platforms 
like NotebookLM can contribute to improving the onboarding experience, potentially empowering JKDM officers and 
supporting a more efficient and effective customs administration.  

4. 
Proposed Implementation Process 
The Malaysian government's existing subscription to Google Workspace provides a strong foundation for the seamless 
implementation of NotebookLM Plus. This integration offers several benefits. Government servants are already accustomed 
to navigating and utilizing various Google Workspace applications, such as Gmail, Google Drive, and Google Docs. This 
existing familiarity with the Google Workspace environment can facilitate a smoother transition and faster adoption of 
NotebookLM Plus, reducing potential resistance to change and encouraging active platform use. Google Workspace is known 
for its stringent security measures designed to protect sensitive data. By integrating NotebookLM Plus with this existing 
infrastructure, the government can leverage these robust security measures to safeguard confidential information and maintain 
data privacy, which is crucial for maintaining public trust and ensuring compliance with data protection regulations. Lastly, 
utilizing the existing Google Workspace infrastructure optimizes resource allocation and potentially reduces implementation 
costs. This cost-effectiveness stems from avoiding the need to invest in new infrastructure or software, allowing for a more 
efficient and economical implementation process, which is particularly important in the context of limited public sector 
budgets. 
Figure 5:  Implementation Process of Job Rotation Powered by Large Language Model 
Successful implementation of NotebookLM Plus necessitates strategic collaboration with key stakeholders, including 
MAMPU, JKDM, Agency IT Departments, and Google Workspace Administrators. It is suggested that MAMPU, as the central 
agency for public sector modernization, provide overarching guidance to ensure alignment with national digital transformation 
policies and strategies. Their involvement is deemed crucial for ensuring the project contributes to broader goals of enhancing 
public sector efficiency and effectiveness. JKDM, possessing specialized knowledge and experience in customs regulations 
and procedures, should contribute customs-specific expertise and content to tailor NotebookLM Plus to their unique 
requirements. Their input is vital to ensure the platform effectively addresses the specific challenges faced by JKDM officers 
during job rotation onboarding. Agency IT departments are expected to play a critical role in the technical setup, integration 
with existing systems, and ongoing support for NotebookLM Plus. Their expertise is essential for ensuring the smooth 
operation and maintenance of the platform within each agency's IT infrastructure. Google Workspace administrators should 
manage user access and permissions within the Google Workspace environment, ensuring data security and privacy. Their role 
is crucial for controlling access to sensitive information and preventing unauthorized use of the platform. 
It is recommended that a pilot program be conducted prior to a full-scale rollout to assess the feasibility and 
effectiveness of NotebookLM Plus in a real-world setting. Specific agencies and departments, including JKDM units, should 
be selected for the pilot program based on their diverse needs and challenges. The selection process should aim to include a 
representative sample of agencies and departments to ensure the pilot program captures a wide range of user experiences and 

potential challenges. The pilot program should have clearly defined objectives, such as assessing the usability of NotebookLM 
Plus, gathering user feedback, and identifying potential challenges. These objectives should guide the data collection and 
analysis process during the pilot phase. The pilot phase should have a specified duration to allow sufficient time for data 
collection and analysis. The duration should be determined based on the scope of the pilot program and the complexity of the 
implementation process. Data should be collected through various methods, including surveys, interviews, and usage analytics, 
to evaluate the effectiveness and user experience of NotebookLM Plus. This data should provide valuable insights into the 
strengths and weaknesses of the platform and inform any necessary adjustments before the full-scale rollout.Feedback from 
the pilot program will be crucial for refining NotebookLM Plus and ensuring that it meets the needs of its users. Feedback will 
be used to enhance the platform's usability and functionality, ensuring it meets the needs of government servants. This may 
involve improving the user interface, adding new features, or modifying existing functionalities based on user suggestions and 
preferences. Learning modules and content will be refined based on user feedback to improve their relevance and effectiveness. 
This may involve updating content, adding new modules, or modifying existing ones to better address the specific learning 
needs of government servants. Any technical or logistical challenges identified during the pilot program will be addressed 
before the department-wide rollout. This may involve resolving technical issues, improving training materials, or addressing 
any logistical barriers to adoption. 
One challenge is the potential resistance to change among government servants. For instance, some employees may 
be hesitant to adopt new technologies due to a perceived lack of technical skills or concerns about job security. To mitigate 
this, comprehensive training and transparent communication are crucial. Training should be hands-on and demonstrate the 
platform's benefits, such as how NotebookLM Plus can simplify tasks and improve efficiency. Transparent communication 
should address concerns openly, perhaps through town hall meetings or online forums where employees can ask questions and 
receive honest answers. A phased rollout can allow employees to adapt gradually, starting with a small group of early adopters 
who can then champion the platform to their colleagues. 
Another challenge is the varying levels of digital literacy among government servants. A recent survey might reveal 
that a significant percentage of employee’s lack confidence in using digital tools or have limited experience with online 
learning platforms. To address this, digital literacy assessments and targeted training programs should be implemented. These 
programs could focus on building essential digital skills, such as navigating online interfaces, using search functions 
effectively, and collaborating on shared documents. Ongoing support through help desks, online resources, and community 
forums can aid employees who encounter difficulties or have further questions. Designing NotebookLM with a user-friendly 
interface, incorporating clear instructions and intuitive navigation, can also accommodate varying digital literacy levels. 
Data privacy concerns are also important to address. A thorough review of existing data privacy policies might reveal 
potential vulnerabilities related to the storage and access of sensitive information within NotebookLM Plus. Safeguards like 
data encryption and access controls should be implemented to prevent unauthorized access and ensure compliance with 
regulations like the Personal Data Protection Act 2010. Data privacy policies should be clearly communicated to foster trust, 
perhaps through easily accessible online documentation or mandatory training modules. Compliance with relevant regulations 
is essential to maintain public confidence and avoid potential legal issues. 
5. 
Result & Impact 
The implementation of NotebookLM Plus is expected to yield significant positive outcomes for the Malaysian 
government. This includes improved onboarding efficiency, as NotebookLM Plus can streamline the onboarding process, 
reducing the time it takes for government servants to become proficient in their new roles. This will lead to faster integration 
and minimize disruptions to service delivery during job rotations (Noe et al., 2017). The platform will facilitate knowledge 
sharing and collaboration among government servants, breaking down information silos and promoting a culture of continuous 
learning. This will lead to a more knowledgeable and adaptable workforce, better equipped to handle the challenges of a 
dynamic public sector environment (Dunleavy et al., 2006). 
Furthermore, NotebookLM Plus is expected to increase productivity by providing quick and easy access to information 
and resources, empowering government servants to work more efficiently and effectively. This will lead to increased 
productivity and improved service delivery to citizens (Davenport & Prusak, 1998). The use of NotebookLM Plus can 
potentially reduce the need for extensive in-person training sessions, leading to cost savings for the government. The platform's 
self-paced learning modules and AI-powered assistance can supplement traditional training methods, making them more 
efficient and cost-effective (Jabatan Perkhidmatan Awam, 2022). A more efficient and effective onboarding process can lead 
to increased employee satisfaction and engagement. By providing the necessary tools and resources for success, NotebookLM 
Plus can contribute to a more positive work environment and improve employee morale. 
In addition to the general benefits for the Malaysian government, the implementation of NotebookLM Plus within 
JKDM is expected to yield specific benefits. NotebookLM Plus will provide JKDM officers with a comprehensive and 
interactive knowledge base of customs regulations, tariffs, and procedures. This will improve their understanding of complex 
regulations and ensure compliance with the latest updates and amendments. The platform's personalized learning paths will 
enable JKDM officers to quickly acquire the knowledge and skills required for different roles within the department. This will 

facilitate smoother transitions between roles and improve their ability to contribute effectively to various areas of customs 
operations. 
Moreover, NotebookLM Plus will enable JKDM officers to perform their duties more efficiently by providing quick 
access to information and resources. This will lead to faster clearance of goods, improved revenue collection, and enhanced 
enforcement of customs regulations. The platform will keep JKDM officers informed about the latest developments in 
international trade and customs regulations. This will enable them to adapt to changes quickly and ensure that JKDM's 
operations remain effective and compliant in a dynamic global trade environment. 
6. 
Key Benefits 
Implementing NotebookLM Plus for onboarding in the Malaysian public sector, particularly within JKDM, offers 
numerous benefits. One significant advantage is enhanced efficiency, leading to streamlined onboarding processes, faster 
learning, and reduced time to proficiency (Noe et al., 2017). This efficiency gain allows employees to integrate into their new 
roles more quickly and contribute effectively to their respective agencies. Another key benefit is improved knowledge transfer, 
facilitated by a centralized knowledge repository, interactive learning modules, and AI-powered assistance (Davenport & 
Prusak, 1998). This enhanced knowledge transfer ensures that employees have access to the information and resources they 
need to perform their duties effectively, leading to better decision-making and improved service delivery. 
NotebookLM Plus can also lead to increased productivity by empowering employees with efficient access to 
information and resources (Janssen et al., 2010). This increased productivity translates to better service delivery and more 
efficient use of public resources. Additionally, the platform offers potential cost savings by reducing the need for extensive in-
person training sessions (Chen et al., 2021). The platform's self-paced learning modules and AI-powered assistance can 
supplement traditional training methods, making them more efficient and cost-effective. Moreover, a more efficient and 
supportive onboarding experience can lead to increased job satisfaction and engagement among employees (Ainin & Ibrahim, 
2013). 
Furthermore, NotebookLM Plus equips employees with the knowledge and skills to navigate a dynamic work 
environment and adapt to evolving job roles (Argote & Ingram, 2000). This adaptability is crucial in today's rapidly changing 
world, where public sector employees need to be able to respond effectively to new challenges and opportunities. Within 
JKDM, the platform can enhance compliance by improving understanding and adherence to complex regulations (Zakaria & 
Ahmad, 2021). This improved compliance can lead to better enforcement of customs regulations and more efficient revenue 
collection. Access to comprehensive information and AI-powered insights also supports better decision-making, leading to 
more informed and effective policies and practices (Dunleavy et al., 2006). By embracing innovative solutions like 
NotebookLM Plus, the Malaysian public sector can enhance its workforce's capabilities, improve service delivery, and 
strengthen its position in a rapidly evolving world. 
Figure 6: Expected Benefits from Large Language Model Deployment for Job Rotation. 

7. 
Conclusion 
This research has explored the intricate challenges surrounding job rotation onboarding in the Malaysian public sector, 
with a specific focus on the Jabatan Kastam Diraja Malaysia (JKDM).  By meticulously examining the complexities of customs 
regulations, the diverse roles within the department, and the ever-evolving nature of the trade environment, this study has 
illuminated the critical need for innovative solutions to enhance onboarding processes and facilitate knowledge transfer.  
Traditional onboarding methods, often characterized by passive learning approaches and limited opportunities for interaction, 
have proven inadequate in ensuring knowledge retention and the effective application of acquired information.  Furthermore, 
time constraints, inconsistencies in onboarding experiences, and the imperative to address varying levels of digital literacy 
among civil servants present formidable obstacles to achieving effective onboarding.     
The proposed solution, harnessing the advanced capabilities of an LLM product, like NotebookLM, offers a compelling 
pathway to navigate these challenges.  NotebookLM is a Google product within the LLM family that allows for document 
ingestion and summarization, interactive training modules, and AI-powered Q&A.  An LLM product provides a 
comprehensive suite of features, encompassing interactive learning modules, AI-powered Q&A systems, and personalized 
learning paths, meticulously crafted to redefine the onboarding experience and empower government servants with the 
knowledge and skills indispensable for excelling in their roles.  The platform's capacity to establish a centralized knowledge 
repository, digitize and organize critical documents, and furnish on-demand support has the potential to revolutionize the 
efficiency and effectiveness of onboarding processes.     
The implementation of an LLM product is poised to yield substantial positive outcomes for the Malaysian public 
sector, extending beyond enhanced onboarding efficiency to encompass heightened knowledge sharing, augmented 
productivity, and cost optimization.  By fostering a more informed, adaptable, and engaged workforce, an LLM product can 
contribute to the delivery of more impactful and efficient public services, ultimately bolstering the Malaysian government's 
ability to navigate the complexities of an increasingly interconnected and rapidly changing world.     
While acknowledging the potential hurdles and limitations inherent in the adoption of any nascent technology, this 
research underscores the profound potential benefits of an LLM product, like NotebookLM, and champions its continued 
exploration and integration within the Malaysian public sector.  
 By embracing innovative solutions such as an LLM product, the Malaysian public sector not only elevates its 
workforce's capabilities and refines service delivery but also fortifies its position as a frontrunner in the digital age.  This 
research serves as a clarion call, imploring policymakers and stakeholders to embrace the transformative potential of an LLM 
product and to proactively champion its implementation, thereby cultivating a more resilient, agile, and citizen-centric public 
service. 

8. 
Reference 
Acemoglu, D., & Autor, D. H. (2011). Skills, tasks and technologies: Implications for employment and earnings. 
Handbook of labor economics, 4, 1043-1171.    
Acemoglu, D., & Restrepo, P. (2018). Artificial intelligence, automation and work. NBER Working Paper No. 24196.    
Agrawal, A., Gans, J. S., & Goldfarb, A. (2019). Prediction machines: The simple economics of artificial intelligence. 
Harvard Business Review Press.    
Al-Shboul, M. R., Abdallah, A. B., & Abdallah, G. (2021). The impact of digital transformation on public sector 
performance: A case study of Malaysia. Journal of Public Administration and Governance, 11(1), 181-201.    
Alshehri, M., & Drew, S. (2023). The impact of artificial intelligence on information privacy: A review. International 
Journal of Information Management, 71, 102642.    
Ananny, M., & Crawford, K. (2018). Seeing without knowing: Limitations of the transparency ideal and its application 
to algorithmic accountability. New Media & Society, 20(3), 973-989.    
Andriopoulos, C., & Lowe, A. (2017). Digital transformation in the public sector: A case study of the UK government. 
International Journal of Public Sector Management, 30(7), 875–892.    
Argote, L., & Ingram, P. (2000). Knowledge transfer: A basis for competitive advantage in firms. Organizational 
Behavior and Human Decision Processes, 82(1), 150–169.    
Autor, D. H. (2015). Why are there still so many jobs? The history and future of workplace automation. Journal of 
Economic Perspectives, 29(3), 3-30.    
Autor, D. H., Levy, F., & Murnane, R. J. (2003). The skill content of recent technological change: An empirical 
exploration. The Quarterly journal of economics, 118(4), 1279-1333.    
Awang, M. M., & Ahmad, K. (2009). Knowledge management initiatives in the Malaysian public sector: A case study 
of the Ministry of Finance. Electronic Journal of Knowledge Management, 7(3), 281-290.    
Baevski, A., et al. (2020). wav2vec 2.0: A framework for self-supervised learning of speech representations. arXiv 
preprint arXiv:2006.11477.    
Bannister, F., & Remenyi, D. (2006). Why IT continues to fail: Addressing the underlying problems. Journal of the 
Operational Research Society, 57(10), 1133–1144.    
Barocas, S., & Selbst, A. D. (2016). Big data's disparate impact. Calif. L. Rev., 104, 671.    
Bauer, T. N., & Erdogan, B. (2011). Organizational socialization: The effective onboarding of new employees. In S. 
Zedeck (Ed.), APA handbook of industrial and organizational psychology, Vol. 2: Selecting and developing members for the 
organization (pp. 505–534). American Psychological Association.    
Benkler, Y. (2006). The wealth of networks: How social production transforms markets and freedom. Yale University 
Press.    
Bentler, P. M., & Speckart, G. (1979). Models of attitude-behavior relations. Psychological review, 86(5), 452.    
Bernama. (2025, February 27). AI at Work 2.0 saves civil servants 3.25 hours a week. New Straits Times.    
Bhattacharjee, A., et al. (2023). Large language models in finance: A survey. arXiv preprint arXiv:2306.06302.    
Biswas, S., et al. (2023). Can large language models be used to assess clinical reasoning skills? arXiv preprint 
arXiv:2304.01567.    
Bommasani, R., et al. (2022). On the opportunities and risks of foundation models. arXiv preprint arXiv:2108.07258.    
Bommasani, R., Hudson, D. A., Adeli, E., Altman, R., Arora, S., von Arx, S., ... & Liang, P. (2021). On the 
opportunities and risks of foundation models. arXiv preprint arXiv:2108.07258.    
Boyd, D., & Crawford, K. (2012). Critical questions for big data: Provocations for a cultural, technological, and 
scholarly phenomenon. Information, Communication & Society, 15(5), 662-679.    
Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., ... & Amodei, D. (2020). Language models 
are few-shot learners. Advances in neural information processing systems, 33, 1877–1901.    
Brynjolfsson, E., & McAfee, A. (2014). The second machine age: Work, progress, and prosperity in a time of brilliant 
technologies. WW Norton & Company.    
Brynjolfsson, E., & Mitchell, T. (2017). What can machine learning do? Workforce implications. Science, 358(6370), 
1530-1534.    
Bubeck, S., et al. (2023). Sparks of artificial general intelligence: Early experiments with gpt-4. arXiv preprint 
arXiv:2303.12712.    
Campion, M. A., Cheraskin, L., & Stevens, M. J. (1994). Career-related antecedents and outcomes of job rotation. 
Academy of Management Journal, 37(6), 1518–1542.    
Caselli, F. (1999). Technological revolutions. American Economic Review, 89(1), 78-102.    
Chen, L., Chen, P., & Lin, Z. (2021). Artificial intelligence in education: A review. IEEE Transactions on Learning 
Technologies, 14(3), 725–739.    
Chowdhery, A., et al. (2022). PaLM: Scaling language modeling with pathways. arXiv preprint arXiv:2204.02311.    
Citron, D. K. (2007). Technological due process. Wash. UL Rev., 85, 1249.    

Clark, K., et al. (2020). ELECTRA: Pre-training text encoders as discriminators rather than generators. arXiv preprint 
arXiv:2003.10555.    
Conneau, A., et al. (2017). Word translation without parallel data. arXiv preprint arXiv:1710.04087.    
CRN Asia. (2025, February 6). Google Cloud empowers nearly half a million civil servants in Malaysia with Gemini 
AI.    
Crawford, K. (2021). Atlas of AI: Power, politics, and the planetary costs of artificial intelligence. Yale University 
Press.    
Dai, Z., et al. (2023). FlashAttention: Fast and memory-efficient exact attention with io-awareness. arXiv preprint 
arXiv:2205.14135.    
Davenport, T. H. (2018). The AI advantage: How to put the artificial intelligence revolution to work. MIT Press.    
Davenport, T. H., & Kirby, J. (2016). Only humans need apply: Winners and losers in the age of smart machines. 
HarperBusiness.    
Davenport, T. H., & Prusak, L. (1998). Working knowledge: How organizations manage what they know. Harvard 
Business Press.    
Devlin, J., et al. (2018). Bert: Pre-training of deep bidirectional transformers for language understanding. arXiv 
preprint arXiv:1810.04805.    
Dodge, J., et al. (2021). Fine-tuning pretrained language models: Weight initializations, data orders, and early stopping. 
arXiv preprint arXiv:2002.06305.    
Dodge, J., Gane, A., Ilharco, G., Pasternack, J., Schlesinger, A., & Weston, J. (2021). Fine-tuning pretrained language 
models: Weight initializations, data orders, and early stopping. arXiv preprint arXiv:2002.06305.    
Drori, I., et al. (2023). A neural corpus indexer for document retrieval. arXiv preprint arXiv:2304.06822.    
Dunleavy, P., Margetts, H., Bastow, S., & Tinkler, J. (2006). Digital era governance: IT corporations, the state, and e-
government. Oxford University Press.    
Economic Planning Unit, Prime Minister's Department. (2010). Tenth Malaysia Plan (2011-2015).    
Economic Planning Unit, Prime Minister's Department. (2015). Eleventh Malaysia Plan (2016-2020).    
Economic Planning Unit, Prime Minister's Department. (2021). Twelfth Malaysia Plan (2021-2025).    
ET CIO SEA. (2025, February 6). Google Cloud and Malaysia's Ministry of Digital launch AI at Work 2.0.    
European Commission. (2021). Ethics guidelines for trustworthy AI.    
Felbo, B., et al. (2017). Using millions of emoji occurrences to learn any-domain representations for detecting 
sentiment, emotion and sarcasm. In Proceedings of the 2017 conference on empirical methods in natural language processing 
(pp. 1615-1625).    
Ford, M. (2015). Rise of the robots: Technology and the threat of a jobless future. Basic Books.    
Frey, C. B. (2019). The technology trap: Capital, labor, and power in the age of automation. Princeton University 
Press.    
Frey, C. B., & Osborne, M. A. (2017). The future of employment: How susceptible are jobs to computerisation? 
Technological Forecasting and Social Change, 114, 254-280.    
Gil-Garcia, J. R., & Pardo, T. A. (2017). Digital government research: A bibliometric analysis and future research 
directions. Government Information Quarterly, 34(2), 271–289.    
Goldin, C. D., & Katz, L. F. (2008). The race between education and technology. Harvard University Press.    
Gordon, R. J. (2016). The rise and fall of American growth: The US standard of living since the Civil War. Princeton 
University Press.    
Hassan, S., & Omar, S. Z. (2018). Talent management practices and employee engagement in the Malaysian public 
sector. Public Personnel Management, 47(1), 3-24.    
Hoffmann, J., Borgeaud, S., Mensch, A., Buchatskaya, E., Cai, T., Rutherford, E., ... & Sifre, L. (2022). Training 
compute-optimal large language models. arXiv preprint arXiv:2203.15556.    
Hoffmann, J., Borgeaud, S., Mensch, A., Buchatskaya, E., Cai, T., Rutherford, E., ... & Sifre, L. (2022). Training 
compute-optimal large language models. arXiv preprint arXiv:2203.15556.    
Holmes, W., Bialik, M., Fadel, C., & Trilling, B. (2023). Artificial intelligence in education. In Data ethics: building 
trust: how digital technologies can serve humanity (pp. 621–653). Globethics Publications.    
Horvitz, E. (2023). On the horizon: Interactive machine learning with large language models. arXiv preprint 
arXiv:2304.05369.    
Huang, M., Zhu, X., & Gao, J. (2023). Large language models for customer service: A survey. arXiv preprint 
arXiv:2301.08678.    
Hussin, H., & Said, J. (2020). Public sector reform in Malaysia: Towards a more responsive and efficient government. 
Journal of Public Affairs, 20(2), e2059.    
Hwang, G. J., Xie, H., Wah, B. W., & Gašević, D. (2020). Vision, challenges, roles and research issues of Artificial 
Intelligence in Education. Computers and Education: Artificial Intelligence, 1, 100001.    

Hwang, G. J., Xie, H., Wah, B. W., & Gašević, D. (2020). Vision, challenges, roles and research issues of Artificial 
Intelligence in Education. Computers and Education: Artificial Intelligence, 1, 100001.    
Jaafar, M., & Ismail, A. (2017). Public sector innovation in Malaysia: The role of leadership. Public Administration 
and Development, 37(2), 111-122. 
Jabatan Kastam Diraja Malaysia. (n.d.). iPatuh. Retrieved March 2, 2025, from https://ipatuh.customs.gov.my/ 
Jabatan Perkhidmatan Awam (JPA). (2011). Human Resource Development Strategic Plan for the Public Service 
(2011-2020). 
Jabatan Perkhidmatan Awam (JPA). (2015). Talent Management Framework for the Public Service. 
Jabatan Perkhidmatan Awam (JPA). (2018). Public Service Competency Framework. 
Jabatan Perkhidmatan Awam (JPA). (2020). Public Service Delivery Transformation Plan. 
Jabatan Perkhidmatan Awam (JPA). (2022). Public Service Circular No. 1 of 2022: Guidelines on the Use of Artificial 
Intelligence in the Public Sector. 
Jabatan Perkhidmatan Awam (JPA). (n.d.). HRMIS. Retrieved March 2, 2025, from https://www.eghrmis.gov.my/ 
Janssen, M., Kuk, G., & Wagenaar, B. (2010). E-government innovation and public sector reform: Impacts, challenges 
and strategies. Edward Elgar Publishing. 
Jin, W., et al. (2023). Is chatgpt a good translator? arXiv preprint arXiv:2301.08745. 
Kaplan, J., et al. (2020). Scaling laws for neural language models. arXiv preprint arXiv:2001.08361. 
Karim, N. S. A., & Ahmad, R. (2010). E-government initiatives in Malaysia: Success factors and challenges. Journal 
of Global Information Technology Management, 13(2), 66-86. 
Katz, L. F., & Murphy, K. M. (1992). Changes in relative wages, 1963-1987: Supply and demand factors. The 
Quarterly Journal of Economics, 107(1), 35-78. 
Keskar, N. S., et al. (2019). On large-batch training for deep learning: Generalization gap and sharp minima. arXiv 
preprint arXiv:1609.04836. 
Kojima, T., et al. (2022). Large language models are zero-shot reasoners. arXiv preprint arXiv:2205.11916. 
Kotter, J. P. (1996). Leading change. Harvard Business Press. 
Kumar, V., Gaur, A., & Upadhyay, S. (2023). The rise of large language models in education: Opportunities, 
challenges, and ethical considerations. In Metaverse for education (pp. 1–27). Academic Press. 
Laloux, F. (2014). Reinventing organizations: A guide to creating organizations inspired by the next stage of human 
consciousness. Nelson Parker. 
Lan, Z., et al. (2019). Albert: A lite bert for self-supervised learning of language representations. arXiv preprint 
arXiv:1909.11942. 
Lee, J., et al. (2023). Summarizing medical conversations using large language models. arXiv preprint 
arXiv:2304.02015. 
Lessig, L. (1999). Code and other laws of cyberspace. Basic Books. 
Lessig, L. (2006). Code: Version 2.0. Basic Books. 
Lewin, K. (1947). Frontiers in group dynamics: Concept, method and reality in social science; social equilibria and 
social change. Human relations, 1(1), 5–41. 
Lewis, M., et al. (2019). BART: Denoising sequence-to-sequence pre-training for natural language generation, 
translation, and comprehension. arXiv preprint arXiv:1910.13461. 
Li, H., Xiong, W., Wang, M., & Zhang, Y. (2023). A survey on large language models for healthcare. arXiv preprint 
arXiv:2304.01097. 
Li, M., et al. (2023). A survey of large language models. arXiv preprint arXiv:2303.18223. 
Liu, Y., et al. (2019). RoBERTa: A robustly optimized bert pretraining approach. arXiv preprint arXiv:1907.11692. 
Maelah, R., & Idris, K. (2015). Human resource management practices and organizational commitment in the 
Malaysian public sector. International Journal of Public Sector Management, 28(3), 225-240. 
Malaysian Administrative Modernisation and Management Planning Unit (MAMPU). (2010). Public Sector 
Transformation: A Roadmap for the Future. 
Malaysian Administrative Modernisation and Management Planning Unit (MAMPU). (2014). Public Sector 
Innovation Policy. 
Malaysian Administrative Modernisation and Management Planning Unit (MAMPU). (2019). Digital Government 
Transformation Framework. 
Malaysian Administrative Modernisation and Management Planning Unit (MAMPU). (n.d.). MyPortfolio: Public 
Sector Work Guidelines. Retrieved March 2, 2025, from https://www.malaysia.gov.my/portal/content/30599 
Manyika, J., Lund, S., Chui, M., Bughin, J., Woetzel, J., Batra, P., ... & Sanghvi, S. (2017). Jobs lost, jobs gained: 
What the future of work will mean for jobs, skills, and wages. McKinsey Global Institute. 
Mehr, H. (2017). Artificial intelligence for citizen services and government. Accenture. 
Miller, T. (2022). The future is now: Solving the climate crisis with current technology. Moonshot. 
Ministry of Communications and Digital Malaysia. (2022). MyDIGITAL: Malaysia Digital Economy Blueprint. 

Ministry of Digital. (2025, February 5). 445000 Public Officers in Malaysia to Benefit from Generative AI Under the 
'AI at Work 2.0' Initiative by the Ministry of Digital and Google Cloud [Press release]. 
Ministry of Education Malaysia. (2021). Malaysia Education Blueprint 2013-2025 (Higher Education). 
Ministry of Environment and Water Malaysia. (2021). National Environmental Policy. 
Ministry of Finance Malaysia. (2023). Budget 2023: Strengthening Recovery, Facilitating Reforms Towards 
Sustainable Socio-Economic Resilience of Keluarga Malaysia. 
Ministry of Health Malaysia. (2021). National Health Policy. 
Ministry of Home Affairs Malaysia. (2021). National Security Policy. 
Ministry of Human Resources Malaysia. (2021). National Human Resources Policy. 
Ministry of Science, Technology and Innovation (MOSTI). (2021). National Fourth Industrial Revolution (4IR) Policy. 
Mittelstadt, B. D., Allo, P., Taddeo, M., Wachter, S., & Floridi, L. (2016). The ethics of algorithms: Mapping the 
debate. Big Data & Society, 3(2), 2053951716679679. 
Mokyr, J. (2002). The gifts of Athena: Historical origins of the knowledge economy. Princeton University Press. 
Nawi, N. M., & Salleh, M. I. (2021). Digital government transformation in Malaysia: A systematic review. Journal of 
Information and Communication Technology, 20(1), 1-24. 
Noble, S. U. (2018). Algorithms of oppression: How search engines reinforce racism. NYU Press. 
Noe, R. A., Hollenbeck, J. R., Gerhart, B., & Wright, P. M. (2017). Human resource management: Gaining a 
competitive advantage. McGraw-Hill Education. 
Nonaka, I., & Takeuchi, H. (1995). The knowledge-creating company: How Japanese companies create the dynamics 
of innovation. 
Nawi, N. M., & Salleh, M. I. (2021). Digital government transformation in Malaysia: A systematic review. Journal of 
Information and Communication Technology, 20(1), 1-24.  
Noble, S. U. (2018). Algorithms of oppression: How search engines reinforce racism. NYU Press.  
Noe, R. A., Hollenbeck, J. R., Gerhart, B., & Wright, P. M. (2017). Human resource management: Gaining a 
competitive advantage. McGraw-Hill Education.  
Nonaka, I., & Takeuchi, H. (1995). The knowledge-creating company: How Japanese companies create the dynamics 
of innovation.)  
OECD. (2019). Digital government strategies for transforming public services. OECD Publishing. 
OECD. (2023). Recommendation of the Council on Artificial Intelligence. OECD Legal Instruments. 
Omar, S. Z., & Hassan, S. (2019). Digital government transformation in Malaysia: Challenges and opportunities. 
International Journal of Public Sector Management, 32(4), 381-398. 
O'Neil, C. (2016). Weapons of math destruction: How big data increases inequality and threatens democracy. Crown. 
OpenAI. (2023). GPT-4 Technical Report. arXiv preprint arXiv:2303.08774. 
Osman, N., & Shukor, S. A. (2022). Digital Transformation in the Public Sector: A Case Study of the Malaysian 
Administrative Modernisation and Management Planning Unit (MAMPU). International Journal of Public Administration, 
45(14), 1204-1215. 
Pasquale, F. (2015). The black box society: The secret algorithms that control money and information. Harvard 
University Press.    
People Matters Global. (2025, February 5). Inside Malaysia: Boosting AI capabilities in the public sector. 
Peng, Y., Dong, Z., & Wu, F. (2023). Large language models in healthcare: Opportunities and challenges. Briefings 
in Bioinformatics, 24(3), bbad089. 
Peters, M. E., et al. (2018). Deep contextualized word representations. arXiv preprint arXiv:1802.05365. 
Qin, C., et al. (2023). Is chatgpt a general-purpose natural language processing task solver? arXiv preprint 
arXiv:2302.06476. 
Radford, A., et al. (2019). Language models are unsupervised multitask learners. OpenAI blog, 1(8), 9.    
Raffel, C., et al. (2020). Exploring the limits of transfer learning with a unified text-to-text transformer. Journal of 
Machine Learning Research, 21(140), 1-67.    
Rahwan, I. (2018). Society-in-the-loop: Programming the algorithmic social contract. Ethics and Information 
Technology, 20, 5-14.    
Rahman, A. A., & Ahmad, S. (2017). The impact of knowledge management on organizational performance in the 
Malaysian public sector: The mediating role of organizational learning. VINE Journal of Information and Knowledge 
Management Systems, 47(4), 516-534. 
Ramli, R., & Ahmad, S. (2022). Human resource management practices and employee performance in the Malaysian 
public sector: The mediating role of organizational commitment. International Journal of Human Resource Management, 
33(10), 2063-2087. 
Rogers, E. M. (2003). Diffusion of innovations. Simon and Schuster. 
Said, J., Alam, S. S., & Zainuddin, Y. (2016). Public sector reform in Malaysia: Issues and challenges. Journal of 
Public Administration and Governance, 6(2), 110-125. 

Salleh, R., & Ahmad, S. (2010). The impact of human resource management practices on employee performance in 
the Malaysian public sector. International Journal of Business and Management, 5(10), 151-160. 
Schwab, K. (2017). The fourth industrial revolution. Currency. 
Shick, T., et al. (2023). Large language models encode clinical knowledge. arXiv preprint arXiv:2212.13138.    
Sidek, N. M., & Abdullah, M. S. (2018). Innovation in the Malaysian public sector: A review of the literature. 
International Journal of Public Administration, 41(13), 1062-1075. 
Solove, D. J. (2004). Digital person: Technology and privacy in the information age. NYU Press. 
Spence, M. (1973). Job market signaling. The quarterly journal of Economics, 87(3), 355-374. 
Sunstein, C. R. (2018). #Republic: Divided democracy in the age of social media. Princeton University Press. 
Susskind, D. (2020). A world without work: Technology, automation, and how we should respond. Metropolitan 
Books. 
Tamkin, A., Brundage, M., Clark, J., & Ganguli, D. (2021). Understanding the capabilities, limitations, and societal 
impact of large language models. arXiv preprint arXiv:2102.02503.    
Tay, Y., et al. (2022). Efficient transformers: A survey. ACM Computing Surveys, 55(6), 1-29. 
Thoppilan, R., et al. (2022). LaMDA: Language models for dialog applications. arXiv preprint arXiv:2201.08239. 
Ting, H. Y., Osman, M. M., & Ting, I. W. K. (2016). E-government adoption in Malaysia: A review of critical factors. 
Transforming Government: People, Process and Policy, 10(1), 126-146. 
Touvron, H., et al. (2023). LLaMA: Open and efficient foundation language models. arXiv preprint arXiv:2302.13971.    
United Nations. (2021). Our Common Agenda. 
Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., ... & Polosukhin, I. (2017). Attention is 
all you need. Advances in neural information processing systems, 30.    
Wei, J., et al. (2022). Chain of thought prompting elicits reasoning in large language models. arXiv preprint 
arXiv:2201.11903. 
World Economic Forum. (2020). The future of jobs report 2020. 
Xu, A., Liu, Z., Guo, Y., Sinha, V., & Akkiraju, R. (2023). Do users benefit from interpretable chatbot? a case study 
on mental health support. In Proceedings of the 2023 CHI Conference on Human Factors in Computing Systems (pp. 1–15). 
Yang, Z., et al. (2023). Harnessing the power of large language models in drug discovery: Opportunities, challenges, 
and future directions. Briefings in Bioinformatics, 24(3), bbad100. 
Yeung, K. (2019). Hypernudge: Big data as a mode of regulation by design. Information, Communication & Society, 
22(7), 1001-1016.    
Yusof, I., & Rahman, H. A. (2010). Public sector innovation in Malaysia: A case study of the Malaysian Administrative 
Modernisation and Management Planning Unit (MAMPU). Public Administration and Development, 30(4), 290-301. 
Yusoff, Y. M., & Hassan, Z. (2010). Knowledge sharing practices in the Malaysian public sector. Journal of 
Knowledge Management Practice, 11(2), 1-10. 
Yusoff, Y. M., & Hassan, Z. (2019). Knowledge sharing and organizational citizenship behavior in the Malaysian 
public sector. Journal of Workplace Learning, 31(1), 64-77. 
Zakaria, N. H., & Ahmad, S. (2021). Knowledge management practices and organizational performance in the 
Malaysian public sector: The mediating role of innovation capability. Journal of Knowledge Management, 25(1), 101-120. 
Zarsky, T. Z. (2016). The law and policy of algorithmic fairness. Science, 352(6294), 1616-1616. 
Zhang, S., et al. (2023). Automatic generation of medical imaging reports using large language models. arXiv preprint 
arXiv:2304.06145. 
Zhong, M., et al. (2023). Large language models for software engineering: A systematic literature review. arXiv 
preprint arXiv:2307.03488. 
Ziegler, D. M., et al. (2023). Fine-tuning language models from human preferences. arXiv preprint arXiv:1909.08593. 
Zuboff, S. (2019). The age of surveillance capitalism: The fight for a human future at the new frontier of power. 
PublicAffairs. 

