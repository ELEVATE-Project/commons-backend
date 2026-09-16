def get_first_page_html(profile, project, voice_provider, story, story_vernacular, flow):
    profile_addresses=None
    translation_json = story_vernacular.translation_json
    if translation_json:
        translation_json = translation_json.get('first_page', {})
    else:
        translation_json = {}

    company_logo = translation_json.get('main_logo', '')
    if profile and profile.first_name:
        profile_addresses = profile.profile_address.all().first()
    #     company_logo = profile.company.get_public_url()
    # else:
    #     company_logo = voice_provider.company_bot.company.get_public_url()
    print("logo: ", company_logo)
    current_state = profile_addresses.state if profile_addresses else ""

    address_string = story.other_params.get('location', '') if story.other_params else ''
    if not address_string:
        address_string = story.location if story.location else ''

    print("current_state: ", current_state)
    if project:
        title = project.get('expected_title') or project.get('actual_title') or "Improvement_story"
    elif story:
        title = story.title if story.title else "Improvement_story"
    else:
        title = "Improvement_story"

    author = story.other_params.get('user_name', '') if story.other_params else ''

    if profile_addresses and profile_addresses.state and profile_addresses.state.lower() == 'nagaland':
        html = f"""
        <div class="story-company-div-fmt1 page-break">
            <div class="story-logo-div2">
              <div class="nagaland-logo-div">
                  <img src="https://static-media.gritworks.ai/fe-images/PNG/Shikshalokam/Samagra_Shiksha_new_bg_removed.png" 
                      style="width: 200px; height: auto; object-fit: contain;"
                      alt="Logo 1">
              
                  <img src="https://static-media.gritworks.ai/fe-images/PNG/Shikshalokam/Nagaland.png" 
                      style="width: 200px; height: auto; object-fit: contain;"
                      alt="Logo 2">
              
                  <img src="https://static-media.gritworks.ai/fe-images/PNG/Shikshalokam/SCERT nagaland.png" 
                      style="width: 200px; height: auto; object-fit: contain;"
                      alt="Logo 3">
              </div>

                <h2 style="font-size: 2.8rem; margin: 20px 0; color: #333; font-weight: bold; text-align: center;">
                    {title}
                </h2>
                <div class="nagaland-image-div"> 
                    <img src="{translation_json.get('nagaland_logo', '')}"
                        class="story-bg1-fmt1" alt="pdf_bg1">
                    </img>
                    </div>
                <div style="margin-top: 15px; text-align: center;">
                    <p style="font-size: 1.2rem; margin: 5px 0; color: #555;">{author}</p>
                    <p style="font-size: 1rem; color: #666; margin: 5px 0;">{address_string}</p>
                </div>
            </div>
            <div  class="nagaland-company-logo-div">
                <img src="https://static-media.gritworks.ai/fe-images/PNG/Shikshalokam/shikshalokam_logo_pdf.png" 
                    style="width: 200px; height: auto; object-fit: contain;"
                alt="Logo 1">
                
                <img src="https://static-media.gritworks.ai/fe-images/PNG/Shikshalokam/shikshagrahaLogo_bg_removed.png" 
                    style="width: 200px; height: auto; object-fit: contain;"
                alt="Logo 2">
            </div>
        </div>
        """
    else:
        html = f"""
        <div class="story-company-div-fmt1 page-break">
            <div class="story-logo-div2">
                <div style="width: 100%; margin-top: 40px;">
                    <div style="display: flex; justify-content: center;">
                        <img src="{company_logo}" 
                            style="width: 300px; height: auto; object-fit: contain;"
                            alt="Bottom Logo">
                    </div>
                </div>
    
                <h2 style="font-size: 2.8rem; margin: 20px 0; color: #333; font-weight: bold; text-align: center;">
                    {title}
                </h2>
                <div class="nagaland-image-div"> 
                    <img src="{translation_json.get('mi_logo', '')}"
                        class="story-bg1-fmt1" alt="pdf_bg1">
                    </img>
                    </div>
                <div style="margin-top: 15px; text-align: center;">
                    <p style="font-size: 1.2rem; margin: 5px 0; color: #555;">{author}</p>
                    <p style="font-size: 1rem; color: #666; margin: 5px 0;">{address_string}</p>
                </div>
            </div>
        </div>
        """
    return html
