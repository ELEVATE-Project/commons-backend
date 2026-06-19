from django.db.models import Q

from chatbot.models import Company, CompanyChat

filtered_names = ['NAGASHETTY BHADRASHETTY','Madhavi','Shankarayya Hiremath','Jayalaxmi','MALKANNA HACHCHADAD','ZOHRA KHANUM','Vandana','Ganapati Bhat','ASHWINI','Vinutha','Savitha','Dinesh Reddy','PRABHUGOUDA','Shashikala','Vijayashree','Sarah','Joffin','Shabana Yasmeen','Anurag','Khrielavonuo','Khayal Sharma','Vijayalaxmi','Archana Hegde','Indira Badiger','Irayya Hiremath','Chubalemla Chang','SRIKRISHNA SETTY','maruti','Rajshekhar S M','Narsappa Rahul','MOHAMMAD RAFI TAWARGERI','Yizano kikon','JAGADISH','Ramesh Rathod','T Akali Kibami','Srinivasa R V','MALAPPA PUJARI','NAIKAR VEENA','Pusazonu','Mansi','Medozhonu','Bhumika','Joyeeta','Sanjana','SHUKURMIYA M','Patrick','Shivaraj','Manjula','GURUDEVI','RAVI F JORAPUR','Dennis','Noyingi Lotha','Sachin','Shrishail','Ankit','Sevanta','Benchumlo H','Aruna','Manoj','Moainla Murry','Aishwarya','Usha','SOMANATH','Menukul Kin','Shalini','fathima','Priyanka','Suhasini','Dhanalakshmi Koneti','Padma','Vishal','Mallikarjun B Kawali','Suhaib','Shravan','Ashima','Venkatesha B','Aditya','Vimeü Miachieo','NINGAPPA SANNAKKI','Rajeshwari','Mainak','Chakjemmenba','A Aotula Lemtur','Basavaraj','Kevisano maria','JAFFAR SHAREEF','HONNAPPA KAMBAR','Zehra','Saraswati','Tiarenla Imchen','Dr.Gururaj Agnihotri','Archana','Ruth kemp','Zuchobeni','JUBRAIL MULLA','RAJAMAHAMMAD KODIHAL','Hardik','Chennamsetty naveen','Shruthi','Bijano','Ajanthung','Basavaraj S','Sonal','Rohan','Smt H L Kademani','smt susheela','Suresh Walikar','Balakrishna','Imtilemla','Naveen','Praveen rao','Kunal','Merentula Imsong','Nzanmongi','Maruti','Bharati','Vijay','Channaveerayyaa D Hiremath','SUREKHA','thippeswmy kv','ashwin','Gauri','Imnawapang','Akash','Mahadev','Nikhil Gehlot','vijay','Bhimashankar','RAJAKUMAR PATIL','SALOMI  L Achumi','Shameem Banu','Pooja','Modi','Vishalaxi','Zachamo','Rajshekhar S Melashetty BRP','Anupriya','Annapurna','Ramesh','Chetan','Lakshmi','Mister Manusch','Master Singh','Rigi','Anisha','Sanjeev','Athrongla','Ramabai','BASAVARAJ','Ram','Arun','Raj','Kumar','Channakeshava VP','Anilkumar','Mohit','Ramappa Navhi','Shesh','Mhashekhoto','Yallappa','Vibha Rawat','Murali','Shaila','Amoghavarsh','Mohit 782','sudhakar','smt Siddamma d hebbal','Vinay','Stephen','Sreeja','Bhavya','Roopa M','Kivitoli sumi','Prateek Agarwal','Nidhi','Pangzungmar','Bendangla Ao','Nithya','Imlisenla Longchar','Lorem','Shivakumar Parashatti','Zechano Z Khuvung','Mansa','Niveditha','SANJAY KUMAR']

company_slug = 'shikshalokam'

company = Company.objects.get(slug=company_slug)
company_chats = CompanyChat.objects.filter(
    (
            Q(sender__company=company) & Q(sender__first_name__in=filtered_names)
    ) |
    (
            Q(receiver__company=company) & Q(receiver__first_name__in=filtered_names)
    )
)

sessions = company_chats.values_list('session', flat=True).distinct()
print(sessions)
