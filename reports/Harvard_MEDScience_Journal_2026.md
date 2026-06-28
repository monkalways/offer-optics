2026-06-23 22:29
Tags: [[Summer Camps]]

# Harvard Medscience Journal
## Day 1
### 1: Patient Maggie and Herniated Disk
There was a dummy, serving as the patient sitting on a crash cart with a bedside monitor beside them. This acted as the patient we were supposed to diagnose. When we met the patient, we asked it some questions to determine the symptoms, what actually occurred and previous medical history, etc. We also determined the vitals using the bedside monitor and compared it with the standard vitals. This patient, Maggie, developed lower back pain from lifting heavy boxes while moving. It was described as radiating from her lower back into her thighs. She later wet herself, showing how she didn't have control of her bowel movements. 

From these symptoms, we ordered an X-ray to be done on her lower back (in actuality, the x-ray was prepared as Maggie is not a real person). The X-ray showed that Maggie had a herniated disk, since there was a protrusion going into her spinal cord, leading to the tingling sensation in her thighs, the pain she felt in her lower back and the reason she couldn't control her bowel movements. 

The suggested methods to cure her herniated disk was physical therapy (PT) to shift the spine vertebrae back into place. 

### 2: Analysis of MoonShot Robot
We investigated the moon shot robot. This robot was made of lego and had an arm that moved forwards and back. The arm could also be rotated left, right, up and down. The robot is controlled via a PS4 controller and the camera vision could be accessed by connecting in the USB-C cable to your laptop. We had to investigate the robot to determine whether this robot would be suited to perform surgeries (why or why not). There were 4 labs: calculate velocity, tool usage, range of motion and vision capabilities. The tools the robot could use were a drill, a curette (a small spoon), a camera and a pair of forceps. 

It turns out that the robot was not suitable to perform surgeries because the robot arm was too shaky, and the increments of motion were too large (surgeries operate on minute scales). 

## Day 2
### 1: Patient Linda & Cancer
Same dummy setup as last time. The dummy, Linda, had reported blood in her pee and had told us that she had previous family history (her mother had breast cancer and her sister has diabetes type II). Her vitals were also normal, other than the raised temperature and blood pressure. She was on blood pressure medication, so the elevated BP was understandable. She also reported lower back pain

Because of the elevated temperature and blood in her pee, we ordered a urine sample. The urine sample showed that there were elevated amounts of WBC and RBC in her pee. This continued to point towards a urinary tract infection (UTI). However, we also performed an x-ray on her, since she also mentioned lower back pain. The x-ray showed a dense mass located inside her bladder. This mass signified a tumor of some sort. It would also explain the symptoms of an UTI. To delve further into this possibility, we ordered a PET (positron emission tomography) scan, which is an advanced imaging test that reveals how your tissues and organs are functioning on a cellular level. Linda then ingested the flurodeoxyglucose, a radioactive tracer, and using the PET scan, we noticed that the areas that were lit up the most were all the standard areas, with an exception of the bladder and the spine. The bright spots indicated the area was using significant amounts of energy, signiftying either high energy consumption, or in some cases, cancer, since they use energy to assist in unregulated cell growth.

Seeing the cancer in her spine was quite concerning as it is quite hard to get rid of the cancer and it poses quite a risk if trying to perform surgery as it is in close proximity to the spinal cord. The tumor in her bladder just required some simple surgery by cutting open the bladder and taking out the tumor. 

There are three different methods to "cure" cancer: radiation therapy, chemotherapy, and surgery. Radiation therapy refers to shining radioactive light onto the target area in hopes of killing the cancer cells in the area. However, this method is quite indiscriminate, leading to cell loss in the target area. Chemotherapy is a treatment where a chemical is injected into your body via an IV and this chemical spreads throughout your entire body. This chemical kills cells that grow and reproduce very quickly (fast cell cycle). This includes hair, nails and, of course, cancer. Surgery is another treatment, but it is quite hard once the cancer is metastatic (stage 4 cancer). 

This connects to the next topic, where we explore the possibilities of integrating robotics into helping patients like Linda with her spine cancer. 

### 2: roboflow AI vision model
We were tasked with creating an AI model that could identify the orange balls (which represent spine cancer) on a patient's spine (using a model spine). We used *roboflow*, a company that helps develop computer vision tools for developers and enterprises. All we had to do was film a video showing different circumstances of the tumor (orange ball), such as "no tumor", "1 tumor", "1 tumor close-up", "2 tumor far-away", etc. Then the video would be split into frames (around 200). The frames would then be hand-annotated by circling the tumors in each of the images. The images are then feed into the model and it begins to train. Once it is done training, we connect it to the robot by using some python code (all provided) and its api key. We then used the robotic arm and the AI vision (shows us where the tumor is) to help extract the tumors from the spine by using the forceps and moving the robot towards it. 

We were then sent to do a test where we simulated the operating room by wearing scrubs with a dummy lying on a table. There was a hole where the spine was placed and, using the robotic arm, we had to remove the tumors within 10 minutes, before the "patient's" anesthetics wore off. 

[Instructions](https://docs.google.com/document/d/1KoXxgyhidsxIed1LtTX2kz347im439Ly0k5rrUFfIss/edit?usp=sharing)

## Day 3
### 1: BioSensors
We learned about the function of sensors and specifically biosensors. These include sphygmomanometer (measure BP), themometers (measures TP), pulse oximeter (measures O2 saturation in blood), etc. We then did a mini lab to help demonstrate the functionality of a pulse oximeter, which shines light through the skin on the fingertip to calculate the percentage of blood carrying oxygen. We mimicked this using a special device that could determine the fluorescence of varying concentrations of a liquid after shining UV light on it. This was similar to how the pulse oximeter uses light to determine oxygen saturation using light.

### 2: OR (Operating Room) Prep
The next activity was learning the different roles of individuals within an operating room to help perform surgery on our patient (Linda) to help remove the tumour in her lung and the blood clot in her right leg. This procedure involves anesthesiologists, cardiothoracic surgeons, pharmacists, a documentor, vascular surgeons and nurses. I played the role of the anesthesiologists, whose primary function is to give the patients appropriate medication (primarily pain-killer and anesthesia). I had to learn how to intubate the patient, which is basically a device that helps the patient breathe while they are unconcious, since they can't breathe anymore. This involves using a laryngoscope (to life the tongue and epiglottis so you can see the vocal cords), the endotracheal tube (ETT) (the tube that goes into the trachea to secure the airway) and the Ambu bag (which pumps oxygen into their lungs). I was also in charge of determining the drugs to give this patient. Since she had low BP and high HR, I had to carefully determine the medication that she could take without adverse side affects. I chose ketamin (pain-killer and anesthesia), epineprine (for emergency only to raise BP, since it also raises HR) and rocuronium (tissue relaxant). 

### 3: OR Drill
After all that preparation, we actually went into a mock operating room to treat Linda. This operating room provided quite the immersive experience for me since they were so many people around me doing their own things to save the patient and also because of the constant beeping of her vitals. 

As the anesthesiologist, I had to perform the intubation on the patient and constantly pump the Ambu bag to provide the patient with oxygen. Furthermore, I also had to keep track of the time to ensure that the next dose of medication would be administered by the nurses before the previous dose wore off. 

All in all, it was quite stressful and I found this experience to be very interesting. The operation lasted for 30 minutes. We were later told that the operating room is usually organized and quiet, quite the contrast to the loud and bustling operating room that we operated in. 

## Day 4
### 1: LLM for Patient Treatment
We worked on how to create an LLM for patient data treatment by giving ChatGPT information regarding some symptoms that patients have and the appropriate treatment plans. The focus for us was primarily orthopedic-related procedures. Our patient was shown to have fluid build-up in the knee and an infection, which we used to correctly diagnosed to be osteomyelitis. 

### 2: Lunch Startup Presentation
At lunch, we listened to a startup found, Meritxell, about her startup called [Averra](https://www.averraag.com/our-team) and her journey. Her journey started in Boston University, where she participated in iGEM (International Genetically Engineered Machine) and created this project which later became Averra. 

### 3: Prepare
We spent the rest of the day preparing our pitch.

## Day 5
### 1: Pitch
During our pitch, we talked about our robot, Nerve-1, and the AI vision model behind it. We tried to tie our presentation to a story to assist in showing the impact of glioblastoma (GBM), an extremely invasive brain cancer, on the lives of real people.

[Script for Pitch](https://docs.google.com/document/d/1J2LvnZCg0ZVa2aGKsIprewRDwNzhkg9exHXA2UJr9aM/edit?tab=t.0)
[Presentation](https://drive.google.com/file/d/1rwBzM0duu76krXn9QIetdTt7TIgplFRY/view?usp=sharing)

### 2: Demo
After our pitch, each of the four investors would come around to the different groups (4 groups) and ask them questions regarding their pitch and watch a small demo. We performed a live demonstration of the removal of a tumor using the robot from the brain. The tumor would then identified by the AI vision model. Unfortunately, our model was only trained on 200 images that had different lighting conditions and post-surgery conditions, and thus, the model couldn't properly identify the tumor during the demonstrations. 

The investors came with questions about our financial situation, would we would do with the additional funding, and our plans for the future. I was in charge of answering the financial questions as well as operating the AI. 


# References
