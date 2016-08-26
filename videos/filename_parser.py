import os
import re
import datetime
import django
from django.utils import timezone
from videos import const
import json
from multiprocessing import Pool, Lock
import fnmatch

django.setup()

from videos.models import Actor, Scene, ActorAlias, SceneTag, Website

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "YAPO.settings")


def filter_alias(actor_alias):
    filtered_alias = list()
    for alias in actor_alias:
        if ' ' in alias.name or alias.is_exempt_from_one_word_search:
            filtered_alias.append(alias)

    return filtered_alias


def if_new_actors():
    actors = list(Actor.objects.filter(date_added__gt=const.LAST_ALL_SCENE_TAG))
    if len(actors) > 0:
        return [True, actors]
    else:
        return [False, actors]


def if_new_alias():
    alias = list(ActorAlias.objects.filter(date_added__gt=const.LAST_ALL_SCENE_TAG))
    if len(alias) > 0:
        return [True, alias]
    else:
        return [False, alias]


def if_new_tags():
    tags = list(SceneTag.objects.filter(date_added__gt=const.LAST_ALL_SCENE_TAG))
    if len(tags) > 0:
        return [True, tags]
    else:
        return [False, tags]


def if_new_websites():
    website = list(Website.objects.filter(date_added__gt=const.LAST_ALL_SCENE_TAG))
    if len(website) > 0:
        return [True, website]
    else:
        return [False, website]


def parse_all_scenes(ignore_last_lookup):
    actors = list(Actor.objects.extra(select={'length': 'Length(name)'}).order_by('-length'))
    actors_alias = list(ActorAlias.objects.extra(select={'length': 'Length(name)'}).order_by('-length'))
    scene_tags = list(SceneTag.objects.extra(select={'length': 'Length(name)'}).order_by('-length'))
    websites = list(Website.objects.extra(select={'length': 'Length(name)'}).order_by('-length'))

    scenes = Scene.objects.all()
    scene_count = scenes.count()
    counter = 1

    if ignore_last_lookup:
        for scene in scenes:
            print("Scene {} out of {}".format(counter, scene_count))

            filtered_alias = filter_alias(actors_alias)

            parse_scene_all_metadata(scene, actors, filtered_alias, scene_tags,
                                     websites)
            counter += 1

    else:
        if const.LAST_ALL_SCENE_TAG:

            a = if_new_actors()
            if a[0]:
                actors = a[1]
                actors.sort(key=lambda x: len(x.name), reverse=True)
            else:
                actors = list()

            b = if_new_alias()
            if b[0]:
                actors_alias = b[1]

                actors_alias = filter_alias(actors_alias)

                actors_alias.sort(key=lambda x: len(x.name), reverse=True)
            else:
                actors_alias = list()

            c = if_new_tags()
            if c[0]:
                scene_tags = c[1]
                scene_tags.sort(key=lambda x: len(x.name), reverse=True)
            else:
                scene_tags = list()

            d = if_new_websites()
            if d[0]:
                websites = d[1]
                websites.sort(key=lambda x: len(x.name), reverse=True)
            else:
                websites = list()

            for scene in scenes:
                print("Scene {} out of {}".format(counter, scene_count))

                if (a[0]) or (b[0]) or (c[0]) or (d[0]):
                    parse_scene_all_metadata(scene, actors, actors_alias, scene_tags,
                                             websites)
                counter += 1

        else:
            for scene in scenes:

                print("Scene {} out of {}".format(counter, scene_count))

                if scene.last_filename_tag_lookup:
                    actors_filtered = list(Actor.objects.filter(date_added__gt=scene.last_filename_tag_lookup))
                    actors_filtered.sort(key=lambda x: len(x.name), reverse=True)

                    actors_alias_filtered = list(
                        ActorAlias.objects.filter(date_added__gt=scene.last_filename_tag_lookup))
                    actors_alias_filtered.sort(key=lambda x: len(x.name), reverse=True)

                    scene_tags_filtered = list(SceneTag.objects.filter(date_added__gt=scene.last_filename_tag_lookup))
                    scene_tags_filtered.sort(key=lambda x: len(x.name), reverse=True)

                    websites_filtered = list(Website.objects.filter(date_added__gt=scene.last_filename_tag_lookup))
                    websites_filtered.sort(key=lambda x: len(x.name), reverse=True)

                    actors_alias_filtered = filter_alias(actors_alias_filtered)

                    parse_scene_all_metadata(scene, actors_filtered, actors_alias_filtered, scene_tags_filtered,
                                             websites_filtered)
                else:

                    filtered_alias = filter_alias(actors_alias)

                    parse_scene_all_metadata(scene, actors, filtered_alias, scene_tags,
                                             websites)
                counter += 1

    f = open('../YAPO/settings.json', 'r')
    x = f.read()
    settings_content = json.loads(x)
    f.close()

    settings_content['last_all_scene_tag'] = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S")

    f = open('../YAPO/settings.json', 'w')
    f.write(json.dumps(settings_content))
    f.close()

    const.LAST_ALL_SCENE_TAG = datetime.datetime.strptime(settings_content['last_all_scene_tag'], "%Y-%m-%d %H:%M:%S")

    print("Finished parsing...")


def parse_scene_all_metadata(scene, actors, actors_alias, scene_tags, websites):
    print("Parsing scene path: {} for actors, tags, and websites...".format(scene.path_to_file))

    scene_path = scene.path_to_file.lower()

    # remove dates from scene path (Maybe later parse dates for scene release dates, right now release dates formats
    # are not consistan through the files)
    # scene_path = re.sub(r'"(.*)(\w+ \d{1,2}, \d{4})"', r'\1', scene_path)

    print("Looking for websites...")
    scene_path = parse_website_in_scenes(scene, scene_path, websites)

    print("Looking for actors and aliases...")
    scene_path = parse_actors_in_scene(scene, scene_path, actors, actors_alias)

    print("Looking for scene tags...")
    scene_path = parse_scene_tags_in_scene(scene, scene_path, scene_tags)

    scene.last_filename_tag_lookup = datetime.datetime.now()

    print("Finished parsing scene: {}'s path... setting Last lookup to {}".format(scene.name,
                                                                                 scene.last_filename_tag_lookup))

    scene.save()


def occurrences(what, string_to_search):
    ans = list()
    can_be_next_occurrence = True
    start_index = 0

    while can_be_next_occurrence:
        try:
            index = string_to_search.index(what, start_index)
            ans.append(index)
            start_index = index + 1
        except ValueError:
            can_be_next_occurrence = False

    return ans


def string_search_without_regex(actor, scene_path):
    ans = {'success': 0, 'scene_path': scene_path}
    actor_name_lower = actor.name.lower()
    string_to_search_in = scene_path

    # scene_path_lower = scene_path.lower()

    # actor_name_lower = actor_name_lower.replace(' ', '?')

    actor_name_split = actor_name_lower.split(' ')

    actor_name_split_backup = list(actor_name_split)
    all_good = False
    total_fail = False
    total_success= False
    name_to_check = actor_name_split[0]

    first_name_occurrences = occurrences(name_to_check, string_to_search_in)
    name_length = len(name_to_check)
    del actor_name_split[0]
    for x in range(len(first_name_occurrences)):
        if not total_success:
            all_good = True
            begin_index = first_name_occurrences[x] + name_length
            actor_name_split_index = 0
            if not total_fail:
                while actor_name_split_index < len(actor_name_split):
                    next_name = actor_name_split[actor_name_split_index]
                    next_name_length = len(next_name)
                    substring = string_to_search_in[begin_index: begin_index + next_name_length + 1]
                    try:
                        index = substring.index(next_name)
                        begin_index = begin_index + index + next_name_length
                        actor_name_split_index += 1
                        if actor_name_split_index >= len(actor_name_split):
                            total_success = True
                    except ValueError:
                        try:
                            last_occurrence = first_name_occurrences[x+1]
                            break
                        except IndexError:
                            actor_name_split_index += 1
                            all_good = False
                            total_fail = True
        else:
            break



    # try:
    #     index = string_to_search_in.index(name_to_check)
    #     name_length = len(name_to_check)
    #     begin_index = index + name_length
    #
    #     del actor_name_split[0]
    #
    #     while actor_name_split != []:
    #         next_name = actor_name_split[0]
    #         next_name_length = len(next_name)
    #         substring = string_to_search_in[begin_index: begin_index + next_name_length + 1]
    #         try:
    #             index = substring.index(next_name)
    #             begin_index = begin_index + index + next_name_length
    #             del actor_name_split[0]
    #         except ValueError:
    #             del actor_name_split[0]
    #             all_good = False
    #
    # except ValueError:
    #     all_good = False
    #
    # while actor_name_split != [] and all_good:
    #     name_to_check = actor_name_split[0]
    #
    #     try:
    #         index = string_to_search_in.index(name_to_check)
    #         name_length = len(name_to_check)
    #
    #         try:
    #             second_name = actor_name_split[1]
    #             second_name_length = len(second_name)
    #             out_index = index + name_length + second_name_length + 1
    #             substring = string_to_search_in[index:out_index]
    #
    #             try:
    #                 second_index = substring.index(second_name)
    #             except ValueError:
    #                 break
    #
    #
    #         except IndexError:
    #             print("no second name")
    #
    #         del actor_name_split[0]
    #     except ValueError:
    #         break

    ans['success'] = all_good

    if all_good:
        for name in actor_name_split_backup:
            scene_path = scene_path.replace(name, '')

    ans['scene_path'] = scene_path
    return ans


def parse_actors_in_scene(scene_to_parse, scene_path, actors, actors_alias):
    # MyModel.objects.extra(select={'length':'Length(name)'}).order_by('length')

    for actor in actors:
        # If actor name is only one word or exempt from being searched even though it is one word.
        # print("     Checking actor {}".format(actor.name))

        if actor.name.count(' ') > 0 or actor.is_exempt_from_one_word_search:
            ans = string_search_without_regex(actor, scene_path)

            if ans['success']:
                scene_path = ans['scene_path']
                add_actor_to_scene(actor, scene_to_parse)

                # regex_search_term = get_regex_search_term(actor.name, ' ')
                #
                # if re.search(regex_search_term, scene_path, re.IGNORECASE) is not None:
                #     # print (actor.name + " is in " + scene_path + "\n")
                #     # scene_path = scene_path.replace(actor.name.lower(), '')
                #     scene_path = re.sub(regex_search_term, '', scene_path, flags=re.IGNORECASE)
                #     # print ("Trimmed scene path is: " + scene_path + "\n")
                #     add_actor_to_scene(actor, scene_to_parse)
                #     # else:
                #     # print (actor.name + " is one word name")

    for alias in actors_alias:
        # print("             Checking alias {}".format(alias.name))
        # actor_in_alias = alias.actors.first()
        # if actor_in_alias:
            if alias.name.count(' ') > 0 or alias.is_exempt_from_one_word_search:
                # regex_search_term = get_regex_search_term(alias.name, ' ')

                    ans = string_search_without_regex(alias, scene_path)

                    if ans['success']:
                        scene_path = ans['scene_path']

                        actor_in_alias = alias.actors.first()
                        print(alias.name + " is alias for " + actor_in_alias.name)
                        add_actor_to_scene(actor_in_alias, scene_to_parse)


                # if re.search(regex_search_term, scene_path, re.IGNORECASE) is not None:
                #     # print (alias.name + " is in " + scene_path + "\n")
                #     # scene_path = scene_path.replace(alias.name.lower(), '')
                #     scene_path = re.sub(regex_search_term, '', scene_path, flags=re.IGNORECASE)
                #     # print ("Trimmed scene path is: " + scene_path + "\n")
                #
                #     print(alias.name + " is alias for " + actor_in_alias.name)
                #     add_actor_to_scene(actor_in_alias, scene_to_parse)
                #     # else:
                #     # print(alias.name + " is one word alias")

    return scene_path


def add_actor_to_scene(actor_to_add, scene_to_add_to):
    # if not Scene.objects.filter(pk=scene_to_add_to.pk, actors__pk=actor_to_add.pk):
    if not scene_to_add_to.actors.filter(pk=actor_to_add.pk):
        print("Adding Actor: {} to the Scene {}".format(actor_to_add.name, scene_to_add_to.name))
        scene_to_add_to.actors.add(actor_to_add)
        scene_to_add_to.save()
    else:
        print("Actor: {} is already registered to scene {}".format(actor_to_add.name,scene_to_add_to.name))


def get_regex_search_term(name, delimiter):
    regex_special_chars = "\+*?[^]$(){}=!<>|:-"
    for char in regex_special_chars:
        if char in name:
            name = name.replace(char, '')
    name_split_list = name.split(delimiter)
    is_first_iteration = True
    regex_search_term = ""
    for part_of_name in name_split_list:

        if is_first_iteration:
            regex_search_term = regex_search_term + part_of_name
            is_first_iteration = False
        else:
            regex_search_term = regex_search_term + ".{0,1}" + part_of_name
            # print ("regex search term is: "  + regex_search_term)
            # regex_search_term =  "r\"" + regex_search_term + "\""
    return regex_search_term


def parse_scene_tags_in_scene(scene, scene_path, scene_tags):
    for scene_tag in scene_tags:
        regex_search_term = get_regex_search_term(scene_tag.name, '.')

        if re.search(regex_search_term, scene_path, re.IGNORECASE) is not None:
            scene_path = re.sub(regex_search_term, '', scene_path, flags=re.IGNORECASE)
            if not scene.scene_tags.filter(name=scene_tag.name):
                print("Adding tag: {} to scene {}".format(scene_tag.name, scene.name))
                # print("Adding " + scene_tag.name + " to scene" + scene.name + "\n")
                scene.scene_tags.add(scene_tag)
            else:
                print("Tag: {} is already in {}".format(scene_tag.name, scene.name))
    return scene_path


def parse_website_in_scenes(scene, scene_path, websites):
    for website in websites:
        regex_search_term = get_regex_search_term(website.name, '.')

        if re.search(regex_search_term, scene_path, re.IGNORECASE) is not None:
            scene_path = re.sub(regex_search_term, '', scene_path, flags=re.IGNORECASE)
            if not scene.websites.filter(name=website.name):
                print("Adding website: " + website.name + " to scene " + scene.name + "\n")
                scene.websites.add(website)

    return scene_path


def clean_taling_spaces():
    actors_to_clean = Actor.objects.all()
    for a_to_clean in actors_to_clean:
        a_to_clean.name = a_to_clean.name.rstrip()
        a_to_clean.save()

    alias_to_clean = ActorAlias.objects.all()
    for al_to_clean in alias_to_clean:
        al_to_clean.name = al_to_clean.name.rstrip()
        al_to_clean.save()

    scene_tags_to_clean = SceneTag.objects.all()
    for s_to_clean in scene_tags_to_clean:
        s_to_clean.name = s_to_clean.name.rstrip()
        s_to_clean.save()


def main():
    parse_all_scenes(False)


if __name__ == "__main__":
    main()
