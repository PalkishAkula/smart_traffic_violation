import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  en: {
    translation: {
      "Drive Defender": "Drive Defender",
      "Welcome to Drive Defender": "Welcome to Drive Defender",
      "Smart Traffic Violation Detection System":
        "Smart Traffic Violation Detection System",
      "Get Started": "Get Started",
      "How it Works": "How it Works",
      Dashboard: "Dashboard",
      Cameras: "Cameras",
      Upload: "Upload",
      Violations: "Violations",
      Instructions: "Instructions",
      Login: "Login",
      Logout: "Logout",
      "Our system uses advanced AI to monitor traffic cameras and automatically detect motorcycle violations such as helmet violations, triple riding, and number plate recognition.":
        "Our system uses advanced AI to monitor traffic cameras and automatically detect motorcycle violations such as helmet violations, triple riding, and number plate recognition.",
      "1. Connect Cameras": "1. Connect Cameras",
      "Add your RTSP IP cameras or upload pre-recorded traffic videos to the system.":
        "Add your RTSP IP cameras or upload pre-recorded traffic videos to the system.",
      "2. AI Processing": "2. AI Processing",
      "Deep learning models analyze frames to detect motorcycles and riders.":
        "Deep learning models analyze frames to detect motorcycles and riders.",
      "3. Detect Violations": "3. Detect Violations",
      "Detects helmet violations, triple riding, and captures vehicle number plates.":
        "Detects helmet violations, triple riding, and captures vehicle number plates.",
      "4. Review & Action": "4. Review & Action",
      "Violations are stored and can be reviewed from the dashboard.":
        "Violations are stored and can be reviewed from the dashboard.",
      Features: "Features",
      "View live statistics and recent violations on the dashboard.":
        "View live statistics and recent violations on the dashboard.",
      "Store and review detected violations with evidence images.":
        "Store and review detected violations with evidence images.",
      "Monitor multiple traffic cameras from a centralized system.":
        "Monitor multiple traffic cameras from a centralized system.",
      "Step-by-step guide to use the traffic violation detection system.":
        "Step-by-step guide to use the traffic violation detection system.",
      "Upload traffic videos to detect motorcycle violations automatically.":
        "Upload traffic videos to detect motorcycle violations automatically.",
      "Welcome to the Drive Defender system. Please follow the instructions below to use the application effectively.":
        "Welcome to the Drive Defender system. Please follow the instructions below to use the application effectively.",
      "1. Creating an Account": "1. Creating an Account",
      "To access the core features of the system, you need to create an account.":
        "To access the core features of the system, you need to create an account.",
      "Click on the 'Login' button in the top right corner of the navigation bar.":
        "Click on the 'Login' button in the top right corner of the navigation bar.",
      "Select 'Don't have an account? Register'.":
        "Select 'Don't have an account? Register'.",
      "Fill in your name, email, and password to register.":
        "Fill in your name, email, and password to register.",
      "2. Adding Cameras": "2. Adding Cameras",
      "Once logged in, you can add traffic cameras to monitor for violations.":
        "Once logged in, you can add traffic cameras to monitor for violations.",
      "Navigate to the 'Cameras' page using the menu.":
        "Navigate to the 'Cameras' page using the menu.",
      "Click 'Add Camera' and provide a Camera ID, Location, and Source.":
        "Click 'Add Camera' and provide a Camera ID, Location, and Source.",
      "For Source, you can use an RTSP URL for IP cameras, or '0' for your local webcam.":
        "For Source, you can use an RTSP URL for IP cameras, or '0' for your local webcam.",
      "The system will start analyzing the live feed immediately.":
        "The system will start analyzing the live feed immediately.",
      "3. Uploading Videos": "3. Uploading Videos",
      "You can also upload pre-recorded videos for violation detection if you don't have a live camera.":
        "You can also upload pre-recorded videos for violation detection if you don't have a live camera.",
      "Go to the 'Upload' page.": "Go to the 'Upload' page.",
      "Drag and drop your video file (supports MP4, AVI, MOV, MKV up to 500MB).":
        "Drag and drop your video file (supports MP4, AVI, MOV, MKV up to 500MB).",
      "Click 'Start Processing' and wait for the AI to analyze the video frames.":
        "Click 'Start Processing' and wait for the AI to analyze the video frames.",
      "View the detailed detection results and statistics upon completion.":
        "View the detailed detection results and statistics upon completion.",
      "4. Managing Violations & Evidence": "4. Managing Violations & Evidence",
      "All detected violations are securely logged and can be reviewed at any time.":
        "All detected violations are securely logged and can be reviewed at any time.",
      "Visit the 'Violations' page to see a comprehensive list of all infractions.":
        "Visit the 'Violations' page to see a comprehensive list of all infractions.",
      "Use the filters at the top to search by license plate, camera ID, date range, or violation type (e.g., No Helmet, Triple Riding).":
        "Use the filters at the top to search by license plate, camera ID, date range, or violation type (e.g., No Helmet, Triple Riding).",
      "Click on the evidence thumbnail image to view a larger version in the Evidence Modal.":
        "Click on the evidence thumbnail image to view a larger version in the Evidence Modal.",
      "You can export the filtered violations data to a CSV file for reporting purposes.":
        "You can export the filtered violations data to a CSV file for reporting purposes.",
      "Need more help?": "Need more help?",
      "Ensure your backend server and ML models are running for the system to function correctly. Check the top right corner for real-time notifications.":
        "Ensure your backend server and ML models are running for the system to function correctly. Check the top right corner for real-time notifications.",
      // Dashboard
      "Total Violations": "Total Violations",
      "all time": "all time",
      Today: "Today",
      "violations today": "violations today",
      "active / total": "active / total",
      "Most Common": "Most Common",
      "violation type": "violation type",
      "Violations — Last 7 Days": "Violations — Last 7 Days",
      "By Violation Type": "By Violation Type",
      "No violations to display": "No violations to display",
      "Recent Violations": "Recent Violations",
      // Cameras page
      "Add Camera": "Add Camera",
      "No cameras added": "No cameras added",
      "Add a camera to start live detection":
        "Add a camera to start live detection",
      "Camera ID": "Camera ID",
      Location: "Location",
      Source: "Source",
      "Enter a number for webcam index or a URL for IP camera":
        "Enter a number for webcam index or a URL for IP camera",
      "All fields are required": "All fields are required",
      "Failed to add camera": "Failed to add camera",
      "Delete camera": "Delete camera",
      "Failed to delete camera": "Failed to delete camera",
      // CameraCard
      "No live feed": "No live feed",
      "View fullscreen": "View fullscreen",
      Start: "Start",
      Stop: "Stop",
      "Stop Camera": "Stop Camera",
      Close: "Close",
      "Camera stopped — no live feed": "Camera stopped — no live feed",
      Unknown: "Unknown",
      "Failed to start camera": "Failed to start camera",
      "Failed to stop camera": "Failed to stop camera",
      // Upload page
      "Upload Video": "Upload Video",
      "Upload a traffic camera video to detect motorcycle violations":
        "Upload a traffic camera video to detect motorcycle violations",
      "Drag & drop your video here": "Drag & drop your video here",
      "or click to browse": "or click to browse",
      "Supports MP4, AVI, MOV, MKV (max 500 MB)":
        "Supports MP4, AVI, MOV, MKV (max 500 MB)",
      Remove: "Remove",
      "Uploading…": "Uploading…",
      "Start Processing": "Start Processing",
      Results: "Results",
      "Upload Another": "Upload Another",
      "Model Logs": "Model Logs",
      lines: "lines",
      Processing: "Processing",
      "Analyzing video…": "Analyzing video…",
      "Processing failed": "Processing failed",
      "Try Again": "Try Again",
      // Violations page
      "Export CSV": "Export CSV",
      "Search plate number...": "Search plate number...",
      "All Cameras": "All Cameras",
      "All Types": "All Types",
      "No Helmet": "No Helmet",
      "Triple Riding": "Triple Riding",
      "Co-rider No Helmet": "Co-rider No Helmet",
      Clear: "Clear",
      Prev: "Prev",
      Next: "Next",
      "total violations": "total violations",
      "Delete violation?": "Delete violation?",
      "This action cannot be undone.": "This action cannot be undone.",
      Track: "Track",
      Plate: "Plate",
      Type: "Type",
      Camera: "Camera",
      Cancel: "Cancel",
      Delete: "Delete",
      "Deleting…": "Deleting…",
      // ViolationTable
      "No violations found": "No violations found",
      Evidence: "Evidence",
      Detected: "Detected",
      Confidence: "Confidence",
      UNDETECTED: "UNDETECTED",
    },
  },
  hi: {
    translation: {
      "Drive Defender": "ड्राइव डिफेंडर",
      "Welcome to Drive Defender": "ड्राइव डिफेंडर में आपका स्वागत है",
      "Smart Traffic Violation Detection System":
        "स्मार्ट यातायात उल्लंघन पहचान प्रणाली",
      "Get Started": "शुरू करें",
      "How it Works": "यह कैसे काम करता है",
      Dashboard: "डैशबोर्ड",
      Cameras: "कैमरे",
      Upload: "अपलोड",
      Violations: "उल्लंघन",
      Instructions: "निर्देश",
      Login: "लॉगिन",
      Logout: "लॉगआउट",
      "Our system uses advanced AI to monitor traffic cameras and automatically detect motorcycle violations such as helmet violations, triple riding, and number plate recognition.":
        "हमारी प्रणाली यातायात कैमरों की निगरानी करने और मोटरसाइकिल उल्लंघनों जैसे हेलमेट उल्लंघन, तीन सवारी और नंबर प्लेट पहचान को स्वचालित रूप से पहचानने के लिए उन्नत AI का उपयोग करती है।",
      "1. Connect Cameras": "1. कैमरे कनेक्ट करें",
      "Add your RTSP IP cameras or upload pre-recorded traffic videos to the system.":
        "अपने RTSP IP कैमरे जोड़ें या सिस्टम में पहले से रिकॉर्ड किए गए ट्रैफिक वीडियो अपलोड करें।",
      "2. AI Processing": "2. AI प्रोसेसिंग",
      "Deep learning models analyze frames to detect motorcycles and riders.":
        "डीप लर्निंग मॉडल मोटरसाइकिलों और सवारों का पता लगाने के लिए फ्रेम का विश्लेषण करते हैं।",
      "3. Detect Violations": "3. उल्लंघन पहचानें",
      "Detects helmet violations, triple riding, and captures vehicle number plates.":
        "हेलमेट उल्लंघन, तीन सवारी का पता लगाता है और वाहन नंबर प्लेट कैप्चर करता है।",
      "4. Review & Action": "4. समीक्षा करें और कार्रवाई करें",
      "Violations are stored and can be reviewed from the dashboard.":
        "उल्लंघन संग्रहीत किए जाते हैं और डैशबोर्ड से समीक्षा की जा सकती है।",
      Features: "विशेषताएं",
      "View live statistics and recent violations on the dashboard.":
        "डैशबोर्ड पर लाइव आंकड़े और हाल के उल्लंघन देखें।",
      "Store and review detected violations with evidence images.":
        "साक्ष्य छवियों के साथ पता लगाए गए उल्लंघनों को संग्रहीत और समीक्षा करें।",
      "Monitor multiple traffic cameras from a centralized system.":
        "एक केंद्रीकृत प्रणाली से कई ट्रैफिक कैमरों की निगरानी करें।",
      "Step-by-step guide to use the traffic violation detection system.":
        "यातायात उल्लंघन पहचान प्रणाली का उपयोग करने के लिए चरण-दर-चरण मार्गदर्शिका।",
      "Upload traffic videos to detect motorcycle violations automatically.":
        "मोटरसाइकिल उल्लंघनों को स्वचालित रूप से पहचानने के लिए ट्रैफिक वीडियो अपलोड करें।",
      "Welcome to the Drive Defender system. Please follow the instructions below to use the application effectively.":
        "ड्राइव डिफेंडर सिस्टम में आपका स्वागत है। एप्लिकेशन का प्रभावी ढंग से उपयोग करने के लिए नीचे दिए गए निर्देशों का पालन करें।",
      "1. Creating an Account": "1. खाता बनाना",
      "To access the core features of the system, you need to create an account.":
        "सिस्टम की मुख्य सुविधाओं तक पहुंचने के लिए, आपको एक खाता बनाना होगा।",
      "Click on the 'Login' button in the top right corner of the navigation bar.":
        "नेविगेशन बार के ऊपरी दाएं कोने में 'लॉगिन' बटन पर क्लिक करें।",
      "Select 'Don't have an account? Register'.":
        "'खाता नहीं है? रजिस्टर करें' चुनें।",
      "Fill in your name, email, and password to register.":
        "रजिस्टर करने के लिए अपना नाम, ईमेल और पासवर्ड भरें।",
      "2. Adding Cameras": "2. कैमरे जोड़ना",
      "Once logged in, you can add traffic cameras to monitor for violations.":
        "लॉग इन करने के बाद, आप उल्लंघनों की निगरानी के लिए ट्रैफिक कैमरे जोड़ सकते हैं।",
      "Navigate to the 'Cameras' page using the menu.":
        "मेनू का उपयोग करके 'कैमरे' पेज पर जाएं।",
      "Click 'Add Camera' and provide a Camera ID, Location, and Source.":
        "'कैमरा जोड़ें' पर क्लिक करें और कैमरा ID, स्थान और स्रोत प्रदान करें।",
      "For Source, you can use an RTSP URL for IP cameras, or '0' for your local webcam.":
        "स्रोत के लिए, आप IP कैमरों के लिए RTSP URL या अपने स्थानीय वेबकैम के लिए '0' का उपयोग कर सकते हैं।",
      "The system will start analyzing the live feed immediately.":
        "सिस्टम तुरंत लाइव फीड का विश्लेषण करना शुरू कर देगा।",
      "3. Uploading Videos": "3. वीडियो अपलोड करना",
      "You can also upload pre-recorded videos for violation detection if you don't have a live camera.":
        "यदि आपके पास लाइव कैमरा नहीं है तो आप उल्लंघन पहचान के लिए पहले से रिकॉर्ड किए गए वीडियो भी अपलोड कर सकते हैं।",
      "Go to the 'Upload' page.": "'अपलोड' पेज पर जाएं।",
      "Drag and drop your video file (supports MP4, AVI, MOV, MKV up to 500MB).":
        "अपनी वीडियो फ़ाइल को खींचें और छोड़ें (500MB तक MP4, AVI, MOV, MKV का समर्थन करता है)।",
      "Click 'Start Processing' and wait for the AI to analyze the video frames.":
        "'प्रोसेसिंग शुरू करें' पर क्लिक करें और AI द्वारा वीडियो फ्रेम का विश्लेषण करने की प्रतीक्षा करें।",
      "View the detailed detection results and statistics upon completion.":
        "पूरा होने पर विस्तृत पहचान परिणाम और आंकड़े देखें।",
      "4. Managing Violations & Evidence":
        "4. उल्लंघन और साक्ष्य प्रबंधित करना",
      "All detected violations are securely logged and can be reviewed at any time.":
        "सभी पता लगाए गए उल्लंघन सुरक्षित रूप से लॉग किए जाते हैं और किसी भी समय समीक्षा की जा सकती है।",
      "Visit the 'Violations' page to see a comprehensive list of all infractions.":
        "सभी उल्लंघनों की व्यापक सूची देखने के लिए 'उल्लंघन' पेज पर जाएं।",
      "Use the filters at the top to search by license plate, camera ID, date range, or violation type (e.g., No Helmet, Triple Riding).":
        "लाइसेंस प्लेट, कैमरा ID, तारीख सीमा, या उल्लंघन प्रकार (जैसे, हेलमेट नहीं, तीन सवारी) से खोजने के लिए शीर्ष पर फ़िल्टर का उपयोग करें।",
      "Click on the evidence thumbnail image to view a larger version in the Evidence Modal.":
        "साक्ष्य मोडल में एक बड़ा संस्करण देखने के लिए साक्ष्य थंबनेल छवि पर क्लिक करें।",
      "You can export the filtered violations data to a CSV file for reporting purposes.":
        "रिपोर्टिंग उद्देश्यों के लिए फ़िल्टर किए गए उल्लंघन डेटा को CSV फ़ाइल में निर्यात कर सकते हैं।",
      "Need more help?": "अधिक मदद चाहिए?",
      "Ensure your backend server and ML models are running for the system to function correctly. Check the top right corner for real-time notifications.":
        "सिस्टम को सही ढंग से काम करने के लिए सुनिश्चित करें कि आपका बैकएंड सर्वर और ML मॉडल चल रहे हैं। रीयल-टाइम सूचनाओं के लिए ऊपरी दाएं कोने की जांच करें।",
      // Dashboard
      "Total Violations": "कुल उल्लंघन",
      "all time": "सभी समय",
      Today: "आज",
      "violations today": "आज के उल्लंघन",
      "active / total": "सक्रिय / कुल",
      "Most Common": "सबसे सामान्य",
      "violation type": "उल्लंघन प्रकार",
      "Violations — Last 7 Days": "उल्लंघन — पिछले 7 दिन",
      "By Violation Type": "उल्लंघन प्रकार के अनुसार",
      "No violations to display": "दिखाने के लिए कोई उल्लंघन नहीं",
      "Recent Violations": "हाल के उल्लंघन",
      // Cameras page
      "Add Camera": "कैमरा जोड़ें",
      "No cameras added": "कोई कैमरा नहीं जोड़ा गया",
      "Add a camera to start live detection":
        "लाइव पहचान शुरू करने के लिए कैमरा जोड़ें",
      "Camera ID": "कैमरा ID",
      Location: "स्थान",
      Source: "स्रोत",
      "Enter a number for webcam index or a URL for IP camera":
        "वेबकैम इंडेक्स के लिए नंबर या IP कैमरे के लिए URL दर्ज करें",
      "All fields are required": "सभी फ़ील्ड आवश्यक हैं",
      "Failed to add camera": "कैमरा जोड़ने में विफल",
      "Delete camera": "कैमरा हटाएं",
      "Failed to delete camera": "कैमरा हटाने में विफल",
      // CameraCard
      "No live feed": "कोई लाइव फीड नहीं",
      "View fullscreen": "पूर्ण स्क्रीन देखें",
      Start: "शुरू करें",
      Stop: "रोकें",
      "Stop Camera": "कैमरा रोकें",
      Close: "बंद करें",
      "Camera stopped — no live feed": "कैमरा रुका — कोई लाइव फीड नहीं",
      Unknown: "अज्ञात",
      "Failed to start camera": "कैमरा शुरू करने में विफल",
      "Failed to stop camera": "कैमरा रोकने में विफल",
      // Upload page
      "Upload Video": "वीडियो अपलोड करें",
      "Upload a traffic camera video to detect motorcycle violations":
        "मोटरसाइकिल उल्लंघनों का पता लगाने के लिए ट्रैफिक कैमरा वीडियो अपलोड करें",
      "Drag & drop your video here": "अपना वीडियो यहाँ खींचें और छोड़ें",
      "or click to browse": "या ब्राउज़ करने के लिए क्लिक करें",
      "Supports MP4, AVI, MOV, MKV (max 500 MB)":
        "MP4, AVI, MOV, MKV समर्थित (अधिकतम 500 MB)",
      Remove: "हटाएं",
      "Uploading…": "अपलोड हो रहा है…",
      "Start Processing": "प्रोसेसिंग शुरू करें",
      Results: "परिणाम",
      "Upload Another": "एक और अपलोड करें",
      "Model Logs": "मॉडल लॉग",
      lines: "पंक्तियाँ",
      Processing: "प्रोसेसिंग",
      "Analyzing video…": "वीडियो का विश्लेषण हो रहा है…",
      "Processing failed": "प्रोसेसिंग विफल",
      "Try Again": "पुनः प्रयास करें",
      // Violations page
      "Export CSV": "CSV निर्यात करें",
      "Search plate number...": "प्लेट नंबर खोजें...",
      "All Cameras": "सभी कैमरे",
      "All Types": "सभी प्रकार",
      "No Helmet": "हेलमेट नहीं",
      "Triple Riding": "तीन सवारी",
      "Co-rider No Helmet": "सह-सवार बिना हेलमेट",
      Clear: "साफ करें",
      Prev: "पिछला",
      Next: "अगला",
      "total violations": "कुल उल्लंघन",
      "Delete violation?": "उल्लंघन हटाएं?",
      "This action cannot be undone.": "यह क्रिया पूर्ववत नहीं की जा सकती।",
      Track: "ट्रैक",
      Plate: "प्लेट",
      Type: "प्रकार",
      Camera: "कैमरा",
      Cancel: "रद्द करें",
      Delete: "हटाएं",
      "Deleting…": "हटाया जा रहा है…",
      // ViolationTable
      "No violations found": "कोई उल्लंघन नहीं मिला",
      Evidence: "साक्ष्य",
      Detected: "पता लगाया",
      Confidence: "विश्वास",
      UNDETECTED: "अज्ञात",
    },
  },
  te: {
    translation: {
      "Drive Defender": "డ్రైవ్ డిఫెండర్",
      "Welcome to Drive Defender": "డ్రైవ్ డిఫెండర్‌కు స్వాగతం",
      "Smart Traffic Violation Detection System":
        "స్మార్ట్ ట్రాఫిక్ ఉల్లంఘన గుర్తింపు వ్యవస్థ",
      "Get Started": "ప్రారంభించండి",
      "How it Works": "ఇది ఎలా పని చేస్తుంది",
      Dashboard: "డాష్‌బోర్డ్",
      Cameras: "కెమెరాలు",
      Upload: "అప్‌లోడ్",
      Violations: "ఉల్లంఘనలు",
      Instructions: "సూచనలు",
      Login: "లాగిన్",
      Logout: "లాగవుట్",
      "Our system uses advanced AI to monitor traffic cameras and automatically detect motorcycle violations such as helmet violations, triple riding, and number plate recognition.":
        "మా వ్యవస్థ ట్రాఫిక్ కెమెరాలను పర్యవేక్షించడానికి మరియు హెల్మెట్ ఉల్లంఘనలు, ట్రిపుల్ రైడింగ్ మరియు నంబర్ ప్లేట్ గుర్తింపు వంటి మోటార్‌సైకిల్ ఉల్లంఘనలను స్వయంచాలకంగా గుర్తించడానికి అధునాతన AIని ఉపయోగిస్తుంది.",
      "1. Connect Cameras": "1. కెమెరాలను కనెక్ట్ చేయండి",
      "Add your RTSP IP cameras or upload pre-recorded traffic videos to the system.":
        "మీ RTSP IP కెమెరాలను జోడించండి లేదా సిస్టమ్‌కు ముందే రికార్డ్ చేసిన ట్రాఫిక్ వీడియోలను అప్‌లోడ్ చేయండి.",
      "2. AI Processing": "2. AI ప్రాసెసింగ్",
      "Deep learning models analyze frames to detect motorcycles and riders.":
        "డీప్ లెర్నింగ్ మోడల్స్ మోటార్‌సైకిళ్ళు మరియు రైడర్లను గుర్తించడానికి ఫ్రేమ్‌లను విశ్లేషిస్తాయి.",
      "3. Detect Violations": "3. ఉల్లంఘనలను గుర్తించండి",
      "Detects helmet violations, triple riding, and captures vehicle number plates.":
        "హెల్మెట్ ఉల్లంఘనలు, ట్రిపుల్ రైడింగ్ గుర్తిస్తుంది మరియు వాహన నంబర్ ప్లేట్లను క్యాప్చర్ చేస్తుంది.",
      "4. Review & Action": "4. సమీక్షించండి & చర్య తీసుకోండి",
      "Violations are stored and can be reviewed from the dashboard.":
        "ఉల్లంఘనలు నిల్వ చేయబడతాయి మరియు డాష్‌బోర్డ్ నుండి సమీక్షించవచ్చు.",
      Features: "లక్షణాలు",
      "View live statistics and recent violations on the dashboard.":
        "డాష్‌బోర్డ్‌లో లైవ్ గణాంకాలు మరియు ఇటీవలి ఉల్లంఘనలను చూడండి.",
      "Store and review detected violations with evidence images.":
        "సాక్ష్య చిత్రాలతో గుర్తించిన ఉల్లంఘనలను నిల్వ చేయండి మరియు సమీక్షించండి.",
      "Monitor multiple traffic cameras from a centralized system.":
        "కేంద్రీకృత వ్యవస్థ నుండి బహుళ ట్రాఫిక్ కెమెరాలను పర్యవేక్షించండి.",
      "Step-by-step guide to use the traffic violation detection system.":
        "ట్రాఫిక్ ఉల్లంఘన గుర్తింపు వ్యవస్థను ఉపయోగించడానికి దశల వారీ గైడ్.",
      "Upload traffic videos to detect motorcycle violations automatically.":
        "మోటార్‌సైకిల్ ఉల్లంఘనలను స్వయంచాలకంగా గుర్తించడానికి ట్రాఫిక్ వీడియోలను అప్‌లోడ్ చేయండి.",
      "Welcome to the Drive Defender system. Please follow the instructions below to use the application effectively.":
        "డ్రైవ్ డిఫెండర్ వ్యవస్థకు స్వాగతం. అప్లికేషన్‌ను సమర్థవంతంగా ఉపయోగించడానికి దయచేసి క్రింది సూచనలను అనుసరించండి.",
      "1. Creating an Account": "1. ఖాతా సృష్టించడం",
      "To access the core features of the system, you need to create an account.":
        "వ్యవస్థ యొక్క ప్రధాన లక్షణాలను యాక్సెస్ చేయడానికి, మీరు ఖాతా సృష్టించాలి.",
      "Click on the 'Login' button in the top right corner of the navigation bar.":
        "నేవిగేషన్ బార్ యొక్క ఎగువ కుడి మూలలో 'లాగిన్' బటన్‌పై క్లిక్ చేయండి.",
      "Select 'Don't have an account? Register'.":
        "'ఖాతా లేదా? నమోదు చేయండి' ఎంచుకోండి.",
      "Fill in your name, email, and password to register.":
        "నమోదు చేయడానికి మీ పేరు, ఇమెయిల్ మరియు పాస్‌వర్డ్ నింపండి.",
      "2. Adding Cameras": "2. కెమెరాలు జోడించడం",
      "Once logged in, you can add traffic cameras to monitor for violations.":
        "లాగిన్ అయిన తర్వాత, ఉల్లంఘనల కోసం పర్యవేక్షించడానికి ట్రాఫిక్ కెమెరాలు జోడించవచ్చు.",
      "Navigate to the 'Cameras' page using the menu.":
        "మెనూ ఉపయోగించి 'కెమెరాలు' పేజీకి వెళ్ళండి.",
      "Click 'Add Camera' and provide a Camera ID, Location, and Source.":
        "'కెమెరా జోడించు' క్లిక్ చేసి కెమెరా ID, స్థానం మరియు మూలం అందించండి.",
      "For Source, you can use an RTSP URL for IP cameras, or '0' for your local webcam.":
        "మూలం కోసం, IP కెమెరాలకు RTSP URL లేదా స్థానిక వెబ్‌కామ్ కోసం '0' ఉపయోగించవచ్చు.",
      "The system will start analyzing the live feed immediately.":
        "వ్యవస్థ వెంటనే లైవ్ ఫీడ్‌ను విశ్లేషించడం ప్రారంభిస్తుంది.",
      "3. Uploading Videos": "3. వీడియోలను అప్‌లోడ్ చేయడం",
      "You can also upload pre-recorded videos for violation detection if you don't have a live camera.":
        "లైవ్ కెమెరా లేకపోయినా ఉల్లంఘన గుర్తింపు కోసం ముందే రికార్డ్ చేసిన వీడియోలను కూడా అప్‌లోడ్ చేయవచ్చు.",
      "Go to the 'Upload' page.": "'అప్‌లోడ్' పేజీకి వెళ్ళండి.",
      "Drag and drop your video file (supports MP4, AVI, MOV, MKV up to 500MB).":
        "మీ వీడియో ఫైల్‌ని లాగి వదలండి (500MB వరకు MP4, AVI, MOV, MKV మద్దతు ఉంది).",
      "Click 'Start Processing' and wait for the AI to analyze the video frames.":
        "'ప్రాసెసింగ్ ప్రారంభించు' క్లిక్ చేసి AI వీడియో ఫ్రేమ్‌లను విశ్లేషించే వరకు వేచి ఉండండి.",
      "View the detailed detection results and statistics upon completion.":
        "పూర్తయిన తర్వాత వివరణాత్మక గుర్తింపు ఫలితాలు మరియు గణాంకాలు చూడండి.",
      "4. Managing Violations & Evidence":
        "4. ఉల్లంఘనలు & సాక్ష్యాలు నిర్వహించడం",
      "All detected violations are securely logged and can be reviewed at any time.":
        "అన్ని గుర్తించిన ఉల్లంఘనలు సురక్షితంగా లాగ్ చేయబడతాయి మరియు ఎప్పుడైనా సమీక్షించవచ్చు.",
      "Visit the 'Violations' page to see a comprehensive list of all infractions.":
        "అన్ని ఉల్లంఘనల సమగ్ర జాబితాను చూడటానికి 'ఉల్లంఘనలు' పేజీని సందర్శించండి.",
      "Use the filters at the top to search by license plate, camera ID, date range, or violation type (e.g., No Helmet, Triple Riding).":
        "లైసెన్స్ ప్లేట్, కెమెరా ID, తేదీ పరిధి లేదా ఉల్లంఘన రకం (ఉదా., హెల్మెట్ లేదు, ట్రిపుల్ రైడింగ్) ద్వారా శోధించడానికి పైన ఉన్న ఫిల్టర్‌లను ఉపయోగించండి.",
      "Click on the evidence thumbnail image to view a larger version in the Evidence Modal.":
        "సాక్ష్య మోడల్‌లో పెద్ద సంస్కరణ చూడటానికి సాక్ష్య థంబ్‌నెయిల్ చిత్రంపై క్లిక్ చేయండి.",
      "You can export the filtered violations data to a CSV file for reporting purposes.":
        "నివేదించే అవసరాలకు ఫిల్టర్ చేసిన ఉల్లంఘన డేటాను CSV ఫైల్‌కు ఎగుమతి చేయవచ్చు.",
      "Need more help?": "మరింత సహాయం కావాలా?",
      "Ensure your backend server and ML models are running for the system to function correctly. Check the top right corner for real-time notifications.":
        "వ్యవస్థ సరిగ్గా పని చేయడానికి మీ బ్యాకెండ్ సర్వర్ మరియు ML మోడల్స్ నడుస్తున్నాయని నిర్ధారించుకోండి. రియల్-టైమ్ నోటిఫికేషన్ల కోసం ఎగువ కుడి మూలను తనిఖీ చేయండి.",
      // Dashboard
      "Total Violations": "మొత్తం ఉల్లంఘనలు",
      "all time": "అన్ని సమయాలు",
      Today: "నేడు",
      "violations today": "నేటి ఉల్లంఘనలు",
      "active / total": "చురుకైన / మొత్తం",
      "Most Common": "అత్యంత సాధారణ",
      "violation type": "ఉల్లంఘన రకం",
      "Violations — Last 7 Days": "ఉల్లంఘనలు — గత 7 రోజులు",
      "By Violation Type": "ఉల్లంఘన రకం ప్రకారం",
      "No violations to display": "చూపించడానికి ఉల్లంఘనలు లేవు",
      "Recent Violations": "ఇటీవలి ఉల్లంఘనలు",
      // Cameras page
      "Add Camera": "కెమెరా జోడించు",
      "No cameras added": "కెమెరాలు జోడించబడలేదు",
      "Add a camera to start live detection":
        "లైవ్ గుర్తింపు ప్రారంభించడానికి కెమెరా జోడించండి",
      "Camera ID": "కెమెరా ID",
      Location: "స్థానం",
      Source: "మూలం",
      "Enter a number for webcam index or a URL for IP camera":
        "వెబ్‌కామ్ ఇండెక్స్ కోసం సంఖ్య లేదా IP కెమెరా కోసం URL నమోదు చేయండి",
      "All fields are required": "అన్ని ఫీల్డ్‌లు అవసరం",
      "Failed to add camera": "కెమెరా జోడించడం విఫలమైంది",
      "Delete camera": "కెమెరా తొలగించు",
      "Failed to delete camera": "కెమెరా తొలగించడం విఫలమైంది",
      // CameraCard
      "No live feed": "లైవ్ ఫీడ్ లేదు",
      "View fullscreen": "పూర్తి స్క్రీన్ చూడండి",
      Start: "ప్రారంభించు",
      Stop: "ఆపు",
      "Stop Camera": "కెమెరా ఆపు",
      Close: "మూసివేయి",
      "Camera stopped — no live feed": "కెమెరా ఆగిపోయింది — లైవ్ ఫీడ్ లేదు",
      Unknown: "తెలియదు",
      "Failed to start camera": "కెమెరా ప్రారంభించడం విఫలమైంది",
      "Failed to stop camera": "కెమెరా ఆపడం విఫలమైంది",
      // Upload page
      "Upload Video": "వీడియో అప్‌లోడ్",
      "Upload a traffic camera video to detect motorcycle violations":
        "మోటార్‌సైకిల్ ఉల్లంఘనలను గుర్తించడానికి ట్రాఫిక్ కెమెరా వీడియో అప్‌లోడ్ చేయండి",
      "Drag & drop your video here": "మీ వీడియోను ఇక్కడ లాగి వదలండి",
      "or click to browse": "లేదా బ్రౌజ్ చేయడానికి క్లిక్ చేయండి",
      "Supports MP4, AVI, MOV, MKV (max 500 MB)":
        "MP4, AVI, MOV, MKV మద్దతు ఉంది (గరిష్టం 500 MB)",
      Remove: "తొలగించు",
      "Uploading…": "అప్‌లోడ్ అవుతోంది…",
      "Start Processing": "ప్రాసెసింగ్ ప్రారంభించు",
      Results: "ఫలితాలు",
      "Upload Another": "మరొకటి అప్‌లోడ్ చేయండి",
      "Model Logs": "మోడల్ లాగ్‌లు",
      lines: "పంక్తులు",
      Processing: "ప్రాసెసింగ్",
      "Analyzing video…": "వీడియో విశ్లేషిస్తోంది…",
      "Processing failed": "ప్రాసెసింగ్ విఫలమైంది",
      "Try Again": "మళ్ళీ ప్రయత్నించండి",
      // Violations page
      "Export CSV": "CSV ఎగుమతి చేయండి",
      "Search plate number...": "ప్లేట్ నంబర్ వెతకండి...",
      "All Cameras": "అన్ని కెమెరాలు",
      "All Types": "అన్ని రకాలు",
      "No Helmet": "హెల్మెట్ లేదు",
      "Triple Riding": "ట్రిపుల్ రైడింగ్",
      "Co-rider No Helmet": "సహ-సవారి హెల్మెట్ లేదు",
      Clear: "క్లియర్ చేయి",
      Prev: "వెనుక",
      Next: "తదుపరి",
      "total violations": "మొత్తం ఉల్లంఘనలు",
      "Delete violation?": "ఉల్లంఘన తొలగించాలా?",
      "This action cannot be undone.": "ఈ చర్యను రద్దు చేయలేరు.",
      Track: "ట్రాక్",
      Plate: "ప్లేట్",
      Type: "రకం",
      Camera: "కెమెరా",
      Cancel: "రద్దు చేయి",
      Delete: "తొలగించు",
      "Deleting…": "తొలగిస్తోంది…",
      // ViolationTable
      "No violations found": "ఉల్లంఘనలు కనుగొనబడలేదు",
      Evidence: "సాక్ష్యం",
      Detected: "గుర్తించబడింది",
      Confidence: "విశ్వాసం",
      UNDETECTED: "గుర్తించబడలేదు",
    },
  },
  ta: {
    translation: {
      "Drive Defender": "டிரைவ் டிஃபெண்டர்",
      "Welcome to Drive Defender": "டிரைவ் டிஃபெண்டருக்கு வரவேற்கிறோம்",
      "Smart Traffic Violation Detection System":
        "ஸ்மார்ட் போக்குவரத்து மீறல் கண்டறிதல் அமைப்பு",
      "Get Started": "தொடங்குங்கள்",
      "How it Works": "இது எப்படி செயல்படுகிறது",
      Dashboard: "டாஷ்போர்டு",
      Cameras: "கேமராக்கள்",
      Upload: "பதிவேற்றம்",
      Violations: "மீறல்கள்",
      Instructions: "வழிமுறைகள்",
      Login: "உள்நுழைவு",
      Logout: "வெளியேறு",
      "Our system uses advanced AI to monitor traffic cameras and automatically detect motorcycle violations such as helmet violations, triple riding, and number plate recognition.":
        "எங்கள் அமைப்பு போக்குவரத்து கேமராக்களை கண்காணிக்கவும் ஹெல்மெட் மீறல்கள், மூவர் சவாரி மற்றும் எண் பலகை அங்கீகாரம் போன்ற மோட்டார்சைக்கிள் மீறல்களை தானாக கண்டறியவும் மேம்பட்ட AIஐ பயன்படுத்துகிறது.",
      "1. Connect Cameras": "1. கேமராக்களை இணைக்கவும்",
      "Add your RTSP IP cameras or upload pre-recorded traffic videos to the system.":
        "உங்கள் RTSP IP கேமராக்களை சேர்க்கவும் அல்லது முன்பே பதிவுசெய்யப்பட்ட போக்குவரத்து வீடியோக்களை கணினியில் பதிவேற்றவும்.",
      "2. AI Processing": "2. AI செயலாக்கம்",
      "Deep learning models analyze frames to detect motorcycles and riders.":
        "டீப் லேர்னிங் மாடல்கள் மோட்டார்சைக்கிள்கள் மற்றும் சவாரியாளர்களை கண்டறிய ஃப்ரேம்களை பகுப்பாய்வு செய்கின்றன.",
      "3. Detect Violations": "3. மீறல்களை கண்டறியவும்",
      "Detects helmet violations, triple riding, and captures vehicle number plates.":
        "ஹெல்மெட் மீறல்கள், மூவர் சவாரியை கண்டறிந்து வாகன எண் பலகைகளை படம்பிடிக்கிறது.",
      "4. Review & Action": "4. மதிப்பாய்வு மற்றும் நடவடிக்கை",
      "Violations are stored and can be reviewed from the dashboard.":
        "மீறல்கள் சேமிக்கப்படுகின்றன மற்றும் டாஷ்போர்டிலிருந்து மதிப்பாய்வு செய்யலாம்.",
      Features: "அம்சங்கள்",
      "View live statistics and recent violations on the dashboard.":
        "டாஷ்போர்டில் நேரடி புள்ளிவிவரங்கள் மற்றும் சமீபத்திய மீறல்களை காணுங்கள்.",
      "Store and review detected violations with evidence images.":
        "சான்று படங்களுடன் கண்டறிந்த மீறல்களை சேமித்து மதிப்பாய்வு செய்யுங்கள்.",
      "Monitor multiple traffic cameras from a centralized system.":
        "மையமான அமைப்பிலிருந்து பல போக்குவரத்து கேமராக்களை கண்காணிக்கவும்.",
      "Step-by-step guide to use the traffic violation detection system.":
        "போக்குவரத்து மீறல் கண்டறிதல் அமைப்பை பயன்படுத்த படிப்படியான வழிகாட்டி.",
      "Upload traffic videos to detect motorcycle violations automatically.":
        "மோட்டார்சைக்கிள் மீறல்களை தானாக கண்டறிய போக்குவரத்து வீடியோக்களை பதிவேற்றவும்.",
      "Welcome to the Drive Defender system. Please follow the instructions below to use the application effectively.":
        "டிரைவ் டிஃபெண்டர் அமைப்பிற்கு வரவேற்கிறோம். பயன்பாட்டை திறம்பட பயன்படுத்த கீழே உள்ள வழிமுறைகளை பின்பற்றவும்.",
      "1. Creating an Account": "1. கணக்கை உருவாக்குதல்",
      "To access the core features of the system, you need to create an account.":
        "அமைப்பின் முக்கிய அம்சங்களை அணுக, நீங்கள் ஒரு கணக்கை உருவாக்க வேண்டும்.",
      "Click on the 'Login' button in the top right corner of the navigation bar.":
        "வழிசெலுத்தல் பட்டியின் மேல் வலது மூலையில் உள்ள 'உள்நுழைவு' பொத்தானை கிளிக் செய்யவும்.",
      "Select 'Don't have an account? Register'.":
        "'கணக்கு இல்லையா? பதிவு செய்யுங்கள்' என்பதை தேர்ந்தெடுக்கவும்.",
      "Fill in your name, email, and password to register.":
        "பதிவு செய்ய உங்கள் பெயர், மின்னஞ்சல் மற்றும் கடவுச்சொல்லை நிரப்பவும்.",
      "2. Adding Cameras": "2. கேமராக்களை சேர்த்தல்",
      "Once logged in, you can add traffic cameras to monitor for violations.":
        "உள்நுழைந்த பிறகு, மீறல்களை கண்காணிக்க போக்குவரத்து கேமராக்களை சேர்க்கலாம்.",
      "Navigate to the 'Cameras' page using the menu.":
        "மெனு பயன்படுத்தி 'கேமராக்கள்' பக்கத்திற்கு செல்லுங்கள்.",
      "Click 'Add Camera' and provide a Camera ID, Location, and Source.":
        "'கேமரா சேர்' என்பதை கிளிக் செய்து கேமரா ID, இடம் மற்றும் மூலத்தை வழங்கவும்.",
      "For Source, you can use an RTSP URL for IP cameras, or '0' for your local webcam.":
        "மூலத்திற்கு, IP கேமராக்களுக்கு RTSP URL அல்லது உங்கள் உள்ளூர் வெப்கேமுக்கு '0' பயன்படுத்தலாம்.",
      "The system will start analyzing the live feed immediately.":
        "அமைப்பு உடனடியாக நேரடி ஊட்டத்தை பகுப்பாய்வு செய்யத் தொடங்கும்.",
      "3. Uploading Videos": "3. வீடியோக்களை பதிவேற்றுதல்",
      "You can also upload pre-recorded videos for violation detection if you don't have a live camera.":
        "நேரடி கேமரா இல்லாவிட்டாலும் மீறல் கண்டறிதலுக்கு முன்பே பதிவுசெய்யப்பட்ட வீடியோக்களையும் பதிவேற்றலாம்.",
      "Go to the 'Upload' page.": "'பதிவேற்றம்' பக்கத்திற்கு செல்லுங்கள்.",
      "Drag and drop your video file (supports MP4, AVI, MOV, MKV up to 500MB).":
        "உங்கள் வீடியோ கோப்பை இழுத்து விடவும் (500MB வரை MP4, AVI, MOV, MKV ஆதரிக்கிறது).",
      "Click 'Start Processing' and wait for the AI to analyze the video frames.":
        "'செயலாக்கத்தை தொடங்கு' என்பதை கிளிக் செய்து AI வீடியோ ஃப்ரேம்களை பகுப்பாய்வு செய்யும் வரை காத்திருக்கவும்.",
      "View the detailed detection results and statistics upon completion.":
        "முடிந்த பிறகு விரிவான கண்டறிதல் முடிவுகள் மற்றும் புள்ளிவிவரங்களை காணுங்கள்.",
      "4. Managing Violations & Evidence":
        "4. மீறல்கள் மற்றும் சான்றுகளை நிர்வகித்தல்",
      "All detected violations are securely logged and can be reviewed at any time.":
        "அனைத்து கண்டறிந்த மீறல்களும் பாதுகாப்பாக பதிவு செய்யப்படுகின்றன மற்றும் எந்த நேரத்திலும் மதிப்பாய்வு செய்யலாம்.",
      "Visit the 'Violations' page to see a comprehensive list of all infractions.":
        "அனைத்து மீறல்களின் விரிவான பட்டியலை காண 'மீறல்கள்' பக்கத்தை பார்வையிடவும்.",
      "Use the filters at the top to search by license plate, camera ID, date range, or violation type (e.g., No Helmet, Triple Riding).":
        "உரிமம் தகடு, கேமரா ID, தேதி வரம்பு அல்லது மீறல் வகை (எ.கா., ஹெல்மெட் இல்லை, மூவர் சவாரி) மூலம் தேட மேலே உள்ள வடிகட்டிகளை பயன்படுத்தவும்.",
      "Click on the evidence thumbnail image to view a larger version in the Evidence Modal.":
        "சான்று மோடலில் பெரிய பதிப்பை காண சான்று சிறுபட திரை படத்தை கிளிக் செய்யவும்.",
      "You can export the filtered violations data to a CSV file for reporting purposes.":
        "அறிக்கை நோக்கங்களுக்கு வடிகட்டிய மீறல் தரவை CSV கோப்பாக ஏற்றுமதி செய்யலாம்.",
      "Need more help?": "மேலும் உதவி வேண்டுமா?",
      "Ensure your backend server and ML models are running for the system to function correctly. Check the top right corner for real-time notifications.":
        "அமைப்பு சரியாக செயல்பட உங்கள் பின்தள சேவையகம் மற்றும் ML மாடல்கள் இயங்குகின்றனவா என்பதை உறுதியாக்கவும். நிகழ்நேர அறிவிப்புகளுக்கு மேல் வலது மூலையை சரிபார்க்கவும்.",
      // Dashboard
      "Total Violations": "மொத்த மீறல்கள்",
      "all time": "எல்லா நேரமும்",
      Today: "இன்று",
      "violations today": "இன்றைய மீறல்கள்",
      "active / total": "செயலில் / மொத்தம்",
      "Most Common": "மிக சாதாரணமான",
      "violation type": "மீறல் வகை",
      "Violations — Last 7 Days": "மீறல்கள் — கடந்த 7 நாட்கள்",
      "By Violation Type": "மீறல் வகை மூலம்",
      "No violations to display": "காட்ட மீறல்கள் இல்லை",
      "Recent Violations": "சமீபத்திய மீறல்கள்",
      // Cameras page
      "Add Camera": "கேமரா சேர்",
      "No cameras added": "கேமராக்கள் சேர்க்கப்படவில்லை",
      "Add a camera to start live detection":
        "நேரடி கண்டறிதல் தொடங்க கேமரா சேர்க்கவும்",
      "Camera ID": "கேமரா ID",
      Location: "இடம்",
      Source: "மூலம்",
      "Enter a number for webcam index or a URL for IP camera":
        "வெப்கேம் இண்டெக்ஸுக்கு எண் அல்லது IP கேமராவுக்கு URL உள்ளிடவும்",
      "All fields are required": "அனைத்து புலங்களும் தேவை",
      "Failed to add camera": "கேமரா சேர்க்க தவறிவிட்டது",
      "Delete camera": "கேமரா நீக்கு",
      "Failed to delete camera": "கேமரா நீக்க தவறிவிட்டது",
      // CameraCard
      "No live feed": "நேரடி ஊட்டம் இல்லை",
      "View fullscreen": "முழு திரை காண்க",
      Start: "தொடங்கு",
      Stop: "நிறுத்து",
      "Stop Camera": "கேமரா நிறுத்து",
      Close: "மூடு",
      "Camera stopped — no live feed":
        "கேமரா நிறுத்தப்பட்டது — நேரடி ஊட்டம் இல்லை",
      Unknown: "தெரியவில்லை",
      "Failed to start camera": "கேமரா தொடங்க தவறிவிட்டது",
      "Failed to stop camera": "கேமரா நிறுத்த தவறிவிட்டது",
      // Upload page
      "Upload Video": "வீடியோ பதிவேற்றம்",
      "Upload a traffic camera video to detect motorcycle violations":
        "மோட்டார்சைக்கிள் மீறல்களை கண்டறிய போக்குவரத்து கேமரா வீடியோ பதிவேற்றவும்",
      "Drag & drop your video here": "உங்கள் வீடியோவை இங்கே இழுத்து விடவும்",
      "or click to browse": "அல்லது உலாவ கிளிக் செய்யவும்",
      "Supports MP4, AVI, MOV, MKV (max 500 MB)":
        "MP4, AVI, MOV, MKV ஆதரிக்கிறது (அதிகபட்சம் 500 MB)",
      Remove: "நீக்கு",
      "Uploading…": "பதிவேற்றுகிறது…",
      "Start Processing": "செயலாக்கம் தொடங்கு",
      Results: "முடிவுகள்",
      "Upload Another": "மற்றொன்று பதிவேற்றவும்",
      "Model Logs": "மாடல் பதிவுகள்",
      lines: "வரிகள்",
      Processing: "செயலாக்கம்",
      "Analyzing video…": "வீடியோ பகுப்பாய்வு செய்கிறது…",
      "Processing failed": "செயலாக்கம் தோல்வியடைந்தது",
      "Try Again": "மீண்டும் முயற்சிக்கவும்",
      // Violations page
      "Export CSV": "CSV ஏற்றுமதி",
      "Search plate number...": "பலகை எண் தேடவும்...",
      "All Cameras": "அனைத்து கேமராக்கள்",
      "All Types": "அனைத்து வகைகள்",
      "No Helmet": "ஹெல்மெட் இல்லை",
      "Triple Riding": "மூவர் சவாரி",
      "Co-rider No Helmet": "சகப்பயணி ஹெல்மெட் இல்லை",
      Clear: "அழி",
      Prev: "முந்தைய",
      Next: "அடுத்த",
      "total violations": "மொத்த மீறல்கள்",
      "Delete violation?": "மீறலை நீக்கவா?",
      "This action cannot be undone.": "இந்த செயலை மாற்ற முடியாது.",
      Track: "ட்ராக்",
      Plate: "பலகை",
      Type: "வகை",
      Camera: "கேமரா",
      Cancel: "ரத்துசெய்",
      Delete: "நீக்கு",
      "Deleting…": "நீக்குகிறது…",
      // ViolationTable
      "No violations found": "மீறல்கள் கண்டுபிடிக்கவில்லை",
      Evidence: "சான்று",
      Detected: "கண்டறியப்பட்டது",
      Confidence: "நம்பகத்தன்மை",
      UNDETECTED: "கண்டறியவில்லை",
    },
  },
  mr: {
    translation: {
      "Drive Defender": "ड्राइव्ह डिफेंडर",
      "Welcome to Drive Defender": "ड्राइव्ह डिफेंडरमध्ये आपले स्वागत आहे",
      "Smart Traffic Violation Detection System":
        "स्मार्ट वाहतूक उल्लंघन शोध प्रणाली",
      "Get Started": "सुरुवात करा",
      "How it Works": "हे कसे कार्य करते",
      Dashboard: "डॅशबोर्ड",
      Cameras: "कॅमेरे",
      Upload: "अपलोड",
      Violations: "उल्लंघने",
      Instructions: "सूचना",
      Login: "लॉगिन",
      Logout: "लॉगआउट",
      "Our system uses advanced AI to monitor traffic cameras and automatically detect motorcycle violations such as helmet violations, triple riding, and number plate recognition.":
        "आमची प्रणाली वाहतूक कॅमेरांचे निरीक्षण करण्यासाठी आणि हेल्मेट उल्लंघने, तिहेरी स्वारी आणि नंबर प्लेट ओळख यासारख्या मोटारसायकल उल्लंघनांचे स्वयंचलितपणे शोध घेण्यासाठी प्रगत AI वापरते.",
      "1. Connect Cameras": "1. कॅमेरे जोडा",
      "Add your RTSP IP cameras or upload pre-recorded traffic videos to the system.":
        "आपले RTSP IP कॅमेरे जोडा किंवा सिस्टममध्ये आधी रेकॉर्ड केलेले ट्रॅफिक व्हिडिओ अपलोड करा.",
      "2. AI Processing": "2. AI प्रक्रिया",
      "Deep learning models analyze frames to detect motorcycles and riders.":
        "डीप लर्निंग मॉडेल्स मोटारसायकली आणि स्वारांना शोधण्यासाठी फ्रेमचे विश्लेषण करतात.",
      "3. Detect Violations": "3. उल्लंघने शोधा",
      "Detects helmet violations, triple riding, and captures vehicle number plates.":
        "हेल्मेट उल्लंघने, तिहेरी स्वारी शोधते आणि वाहन नंबर प्लेट कॅप्चर करते.",
      "4. Review & Action": "4. पुनरावलोकन आणि कार्यवाही",
      "Violations are stored and can be reviewed from the dashboard.":
        "उल्लंघने साठवली जातात आणि डॅशबोर्डवरून पुनरावलोकन करता येते.",
      Features: "वैशिष्ट्ये",
      "View live statistics and recent violations on the dashboard.":
        "डॅशबोर्डवर थेट आकडेवारी आणि अलीकडील उल्लंघने पाहा.",
      "Store and review detected violations with evidence images.":
        "पुरावा प्रतिमांसह शोधलेल्या उल्लंघनांचे संचयन आणि पुनरावलोकन करा.",
      "Monitor multiple traffic cameras from a centralized system.":
        "केंद्रीकृत प्रणालीतून अनेक वाहतूक कॅमेरांचे निरीक्षण करा.",
      "Step-by-step guide to use the traffic violation detection system.":
        "वाहतूक उल्लंघन शोध प्रणाली वापरण्यासाठी चरण-दर-चरण मार्गदर्शिका.",
      "Upload traffic videos to detect motorcycle violations automatically.":
        "मोटारसायकल उल्लंघने स्वयंचलितपणे शोधण्यासाठी ट्रॅफिक व्हिडिओ अपलोड करा.",
      "Welcome to the Drive Defender system. Please follow the instructions below to use the application effectively.":
        "ड्राइव्ह डिफेंडर सिस्टममध्ये आपले स्वागत आहे. अनुप्रयोग प्रभावीपणे वापरण्यासाठी कृपया खालील सूचनांचे पालन करा.",
      "1. Creating an Account": "1. खाते तयार करणे",
      "To access the core features of the system, you need to create an account.":
        "सिस्टमच्या मुख्य वैशिष्ट्यांमध्ये प्रवेश करण्यासाठी, आपल्याला खाते तयार करणे आवश्यक आहे.",
      "Click on the 'Login' button in the top right corner of the navigation bar.":
        "नेव्हिगेशन बारच्या वरच्या उजव्या कोपऱ्यात 'लॉगिन' बटणावर क्लिक करा.",
      "Select 'Don't have an account? Register'.":
        "'खाते नाही? नोंदणी करा' निवडा.",
      "Fill in your name, email, and password to register.":
        "नोंदणी करण्यासाठी आपले नाव, ईमेल आणि पासवर्ड भरा.",
      "2. Adding Cameras": "2. कॅमेरे जोडणे",
      "Once logged in, you can add traffic cameras to monitor for violations.":
        "लॉग इन केल्यानंतर, उल्लंघनांचे निरीक्षण करण्यासाठी वाहतूक कॅमेरे जोडू शकता.",
      "Navigate to the 'Cameras' page using the menu.":
        "मेनू वापरून 'कॅमेरे' पानावर जा.",
      "Click 'Add Camera' and provide a Camera ID, Location, and Source.":
        "'कॅमेरा जोडा' वर क्लिक करा आणि कॅमेरा ID, स्थान आणि स्रोत द्या.",
      "For Source, you can use an RTSP URL for IP cameras, or '0' for your local webcam.":
        "स्रोतासाठी, IP कॅमेरांसाठी RTSP URL किंवा स्थानिक वेबकॅमसाठी '0' वापरू शकता.",
      "The system will start analyzing the live feed immediately.":
        "सिस्टम लगेच थेट फीडचे विश्लेषण सुरू करेल.",
      "3. Uploading Videos": "3. व्हिडिओ अपलोड करणे",
      "You can also upload pre-recorded videos for violation detection if you don't have a live camera.":
        "थेट कॅमेरा नसल्यास उल्लंघन शोधण्यासाठी आधी रेकॉर्ड केलेले व्हिडिओ देखील अपलोड करू शकता.",
      "Go to the 'Upload' page.": "'अपलोड' पानावर जा.",
      "Drag and drop your video file (supports MP4, AVI, MOV, MKV up to 500MB).":
        "आपली व्हिडिओ फाइल ड्रॅग आणि ड्रॉप करा (500MB पर्यंत MP4, AVI, MOV, MKV समर्थित).",
      "Click 'Start Processing' and wait for the AI to analyze the video frames.":
        "'प्रक्रिया सुरू करा' वर क्लिक करा आणि AI व्हिडिओ फ्रेम्सचे विश्लेषण करेपर्यंत प्रतीक्षा करा.",
      "View the detailed detection results and statistics upon completion.":
        "पूर्ण झाल्यावर तपशीलवार शोध परिणाम आणि आकडेवारी पाहा.",
      "4. Managing Violations & Evidence":
        "4. उल्लंघने आणि पुरावे व्यवस्थापित करणे",
      "All detected violations are securely logged and can be reviewed at any time.":
        "सर्व शोधलेली उल्लंघने सुरक्षितपणे नोंदवली जातात आणि कोणत्याही वेळी पुनरावलोकन करता येतात.",
      "Visit the 'Violations' page to see a comprehensive list of all infractions.":
        "सर्व उल्लंघनांची सर्वसमावेशक यादी पाहण्यासाठी 'उल्लंघने' पानाला भेट द्या.",
      "Use the filters at the top to search by license plate, camera ID, date range, or violation type (e.g., No Helmet, Triple Riding).":
        "लायसन्स प्लेट, कॅमेरा ID, तारीख श्रेणी किंवा उल्लंघन प्रकार (उदा., हेल्मेट नाही, तिहेरी स्वारी) नुसार शोधण्यासाठी वरील फिल्टर वापरा.",
      "Click on the evidence thumbnail image to view a larger version in the Evidence Modal.":
        "पुरावा मोडलमध्ये मोठी आवृत्ती पाहण्यासाठी पुरावा थंबनेल प्रतिमेवर क्लिक करा.",
      "You can export the filtered violations data to a CSV file for reporting purposes.":
        "अहवाल उद्देशांसाठी फिल्टर केलेला उल्लंघन डेटा CSV फाइलमध्ये निर्यात करू शकता.",
      "Need more help?": "अधिक मदत हवी आहे का?",
      "Ensure your backend server and ML models are running for the system to function correctly. Check the top right corner for real-time notifications.":
        "सिस्टम योग्यरित्या कार्य करण्यासाठी आपला बॅकएंड सर्वर आणि ML मॉडेल्स चालू असल्याची खात्री करा. रिअल-टाइम सूचनांसाठी वरच्या उजव्या कोपऱ्याची तपासणी करा.",
      // Dashboard
      "Total Violations": "एकूण उल्लंघने",
      "all time": "सर्व वेळ",
      Today: "आज",
      "violations today": "आजची उल्लंघने",
      "active / total": "सक्रिय / एकूण",
      "Most Common": "सर्वात सामान्य",
      "violation type": "उल्लंघन प्रकार",
      "Violations — Last 7 Days": "उल्लंघने — मागील 7 दिवस",
      "By Violation Type": "उल्लंघन प्रकारानुसार",
      "No violations to display": "दाखवण्यासाठी उल्लंघने नाहीत",
      "Recent Violations": "अलीकडील उल्लंघने",
      // Cameras page
      "Add Camera": "कॅमेरा जोडा",
      "No cameras added": "कोणताही कॅमेरा जोडलेला नाही",
      "Add a camera to start live detection":
        "लाइव्ह डिटेक्शन सुरू करण्यासाठी कॅमेरा जोडा",
      "Camera ID": "कॅमेरा ID",
      Location: "स्थान",
      Source: "स्रोत",
      "Enter a number for webcam index or a URL for IP camera":
        "वेबकॅम इंडेक्ससाठी नंबर किंवा IP कॅमेरासाठी URL टाका",
      "All fields are required": "सर्व फील्ड आवश्यक आहेत",
      "Failed to add camera": "कॅमेरा जोडण्यात अयशस्वी",
      "Delete camera": "कॅमेरा हटवा",
      "Failed to delete camera": "कॅमेरा हटवण्यात अयशस्वी",
      // CameraCard
      "No live feed": "कोणताही लाइव्ह फीड नाही",
      "View fullscreen": "पूर्ण स्क्रीन पाहा",
      Start: "सुरू करा",
      Stop: "थांबवा",
      "Stop Camera": "कॅमेरा थांबवा",
      Close: "बंद करा",
      "Camera stopped — no live feed": "कॅमेरा थांबला — लाइव्ह फीड नाही",
      Unknown: "अज्ञात",
      "Failed to start camera": "कॅमेरा सुरू करण्यात अयशस्वी",
      "Failed to stop camera": "कॅमेरा थांबवण्यात अयशस्वी",
      // Upload page
      "Upload Video": "व्हिडिओ अपलोड करा",
      "Upload a traffic camera video to detect motorcycle violations":
        "मोटारसायकल उल्लंघने शोधण्यासाठी ट्रॅफिक कॅमेरा व्हिडिओ अपलोड करा",
      "Drag & drop your video here": "तुमचा व्हिडिओ येथे ड्रॅग करा आणि सोडा",
      "or click to browse": "किंवा ब्राउझ करण्यासाठी क्लिक करा",
      "Supports MP4, AVI, MOV, MKV (max 500 MB)":
        "MP4, AVI, MOV, MKV समर्थित (कमाल 500 MB)",
      Remove: "काढून टाका",
      "Uploading…": "अपलोड होत आहे…",
      "Start Processing": "प्रक्रिया सुरू करा",
      Results: "निकाल",
      "Upload Another": "दुसरे अपलोड करा",
      "Model Logs": "मॉडेल लॉग्स",
      lines: "ओळी",
      Processing: "प्रक्रिया",
      "Analyzing video…": "व्हिडिओ विश्लेषण होत आहे…",
      "Processing failed": "प्रक्रिया अयशस्वी",
      "Try Again": "पुन्हा प्रयत्न करा",
      // Violations page
      "Export CSV": "CSV निर्यात करा",
      "Search plate number...": "प्लेट नंबर शोधा...",
      "All Cameras": "सर्व कॅमेरे",
      "All Types": "सर्व प्रकार",
      "No Helmet": "हेल्मेट नाही",
      "Triple Riding": "तिहेरी स्वारी",
      "Co-rider No Helmet": "सह-स्वारी हेल्मेट नाही",
      Clear: "साफ करा",
      Prev: "मागील",
      Next: "पुढील",
      "total violations": "एकूण उल्लंघने",
      "Delete violation?": "उल्लंघन हटवायचे?",
      "This action cannot be undone.": "ही क्रिया पूर्ववत करता येणार नाही.",
      Track: "ट्रॅक",
      Plate: "प्लेट",
      Type: "प्रकार",
      Camera: "कॅमेरा",
      Cancel: "रद्द करा",
      Delete: "हटवा",
      "Deleting…": "हटवत आहे…",
      // ViolationTable
      "No violations found": "उल्लंघने आढळली नाहीत",
      Evidence: "पुरावा",
      Detected: "आढळले",
      Confidence: "विश्वास",
      UNDETECTED: "अज्ञात",
    },
  },
};

i18n.use(initReactI18next).init({
  resources,
  lng: localStorage.getItem("app_lang") || "en",
  fallbackLng: "en",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
